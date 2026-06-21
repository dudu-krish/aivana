"""
Invoice Matcher Agent

Workflow (from reconciliation agent diagram):
1. Pull invoice and payment data from Excel/CSV files
2. Reconcile — match invoices to payments by amount, reference, vendor
3. Flag mismatches and entries that don't add up
4. Surface only exceptions for human review
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from app.agents.base import BaseAgent
from app.services.event_bus import event_bus
from app.services.tenant import TenantContext

AGENT_ID = "invoice-matcher"
AGENT_NAME = "Invoice Matcher"


def _normalize_ref(value: Any) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _load_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    return pd.read_csv(path)


class InvoiceMatcherAgent(BaseAgent):
    agent_id = AGENT_ID
    agent_name = AGENT_NAME

    def __init__(self, tenant: TenantContext) -> None:
        self.tenant = tenant

    async def _emit(self, event_type: str, message: str, data: dict | None = None):
        return await event_bus.emit(
            self.tenant.user_id, AGENT_ID, AGENT_NAME, event_type, message, data
        )

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        invoices_dir = Path(kwargs.get("invoices_dir", self.tenant.invoices_dir))
        payments_dir = Path(kwargs.get("payments_dir", self.tenant.payments_dir))
        amount_tolerance = float(kwargs.get("amount_tolerance", 0.01))

        await self._emit("started", "Starting invoice reconciliation run")

        invoice_files = sorted(invoices_dir.glob("*.csv")) + sorted(
            invoices_dir.glob("*.xlsx")
        )
        payment_files = sorted(payments_dir.glob("*.csv")) + sorted(
            payments_dir.glob("*.xlsx")
        )

        if not invoice_files:
            await self._emit(
                "error",
                "No invoice files found. Upload your invoice CSV or Excel files first.",
            )
            return {"status": "error", "message": "No invoice files"}

        if not payment_files:
            await self._emit(
                "error",
                "No payment files found. Upload your payment CSV or Excel files first.",
            )
            return {"status": "error", "message": "No payment files"}

        await self._emit(
            "progress",
            f"Pulling data from {len(invoice_files)} invoice and {len(payment_files)} payment file(s)",
        )

        invoices = pd.concat([_load_table(f) for f in invoice_files], ignore_index=True)
        payments = pd.concat([_load_table(f) for f in payment_files], ignore_index=True)

        required_invoice_cols = {"invoice_id", "vendor", "amount", "reference"}
        required_payment_cols = {"payment_id", "vendor", "amount", "reference"}
        if not required_invoice_cols.issubset(invoices.columns):
            missing = required_invoice_cols - set(invoices.columns)
            msg = f"Invoice files missing columns: {', '.join(sorted(missing))}"
            await self._emit("error", msg)
            return {"status": "error", "message": msg}
        if not required_payment_cols.issubset(payments.columns):
            missing = required_payment_cols - set(payments.columns)
            msg = f"Payment files missing columns: {', '.join(sorted(missing))}"
            await self._emit("error", msg)
            return {"status": "error", "message": msg}

        await self._emit(
            "progress",
            f"Loaded {len(invoices)} invoices and {len(payments)} payments — reconciling",
        )

        invoices = invoices.copy()
        payments = payments.copy()
        invoices["_ref_norm"] = invoices["reference"].map(_normalize_ref)
        payments["_ref_norm"] = payments["reference"].map(_normalize_ref)
        invoices["_vendor_norm"] = invoices["vendor"].str.lower().str.strip()
        payments["_vendor_norm"] = payments["vendor"].str.lower().str.strip()

        matched: list[dict[str, Any]] = []
        exceptions: list[dict[str, Any]] = []
        used_payment_ids: set[str] = set()

        for _, inv in invoices.iterrows():
            candidates = payments[
                (payments["_vendor_norm"] == inv["_vendor_norm"])
                & (payments["payment_id"].astype(str).isin(used_payment_ids) == False)  # noqa: E712
            ]

            best_match = None
            best_score = -1

            for _, pay in candidates.iterrows():
                score = 0
                if inv["_ref_norm"] and inv["_ref_norm"] == pay["_ref_norm"]:
                    score += 3
                amount_diff = abs(float(inv["amount"]) - float(pay["amount"]))
                if amount_diff <= amount_tolerance:
                    score += 2
                elif amount_diff <= max(float(inv["amount"]) * 0.05, 1.0):
                    score += 1

                if score > best_score:
                    best_score = score
                    best_match = pay

            if best_match is not None and best_score >= 2:
                amount_diff = abs(float(inv["amount"]) - float(best_match["amount"]))
                match_record = {
                    "invoice_id": str(inv["invoice_id"]),
                    "payment_id": str(best_match["payment_id"]),
                    "vendor": inv["vendor"],
                    "invoice_amount": float(inv["amount"]),
                    "payment_amount": float(best_match["amount"]),
                    "reference": inv["reference"],
                    "amount_diff": round(amount_diff, 2),
                }
                if amount_diff > amount_tolerance:
                    match_record["status"] = "amount_mismatch"
                    exceptions.append(
                        {
                            **match_record,
                            "reason": f"Amount differs by {amount_diff:.2f}",
                        }
                    )
                    await self._emit(
                        "exception",
                        f"Mismatch: invoice {inv['invoice_id']} vs payment {best_match['payment_id']}",
                        match_record,
                    )
                else:
                    match_record["status"] = "matched"
                    matched.append(match_record)
                    await self._emit(
                        "match",
                        f"Matched invoice {inv['invoice_id']} → payment {best_match['payment_id']}",
                        match_record,
                    )
                used_payment_ids.add(str(best_match["payment_id"]))
            else:
                exc = {
                    "invoice_id": str(inv["invoice_id"]),
                    "vendor": inv["vendor"],
                    "invoice_amount": float(inv["amount"]),
                    "reference": inv["reference"],
                    "status": "unmatched_invoice",
                    "reason": "No matching payment found",
                }
                exceptions.append(exc)
                await self._emit(
                    "exception",
                    f"Unmatched invoice {inv['invoice_id']} ({inv['vendor']})",
                    exc,
                )

        for _, pay in payments.iterrows():
            if str(pay["payment_id"]) not in used_payment_ids:
                exc = {
                    "payment_id": str(pay["payment_id"]),
                    "vendor": pay["vendor"],
                    "payment_amount": float(pay["amount"]),
                    "reference": pay["reference"],
                    "status": "unmatched_payment",
                    "reason": "No matching invoice found",
                }
                exceptions.append(exc)
                await self._emit(
                    "exception",
                    f"Unmatched payment {pay['payment_id']} ({pay['vendor']})",
                    exc,
                )

        summary = {
            "status": "completed",
            "total_invoices": len(invoices),
            "total_payments": len(payments),
            "matched": len(matched),
            "exceptions": len(exceptions),
            "matched_records": matched,
            "exception_records": exceptions,
        }

        await self._emit(
            "completed",
            f"Reconciliation done — {len(matched)} matched, {len(exceptions)} exceptions to review",
            {"matched": len(matched), "exceptions": len(exceptions)},
        )
        return summary

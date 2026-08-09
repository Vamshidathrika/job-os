"""Compensation Intelligence package."""

from __future__ import annotations

from jobos.comp.predictor import predict_salary_band
from jobos.comp.deflector import handle_comp_field
from jobos.comp.corpus import SalaryCorpus

__all__ = [
    "predict_salary_band",
    "handle_comp_field",
    "SalaryCorpus",
]

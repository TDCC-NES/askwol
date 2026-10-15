"""Computed data shared by report output formats for one rendering."""

from askwol.models import Status, ValidationReport


class ReportView:
    """Compute findings and external-term groups once per report rendering."""

    def __init__(self, report: ValidationReport) -> None:
        self.summary = report.severity_summary
        self.external_terms = report.external_term_checks
        self.terms_unchecked = report.namespace_resolution_skipped or (
            bool(self.external_terms) and all(term.status == Status.SKIP for _, term in self.external_terms)
        )
        self.external_by_status = {status: [] for status in Status}
        for namespace, term in self.external_terms:
            self.external_by_status[term.status].append((namespace, term))

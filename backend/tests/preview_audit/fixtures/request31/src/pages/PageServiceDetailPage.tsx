import { CompServiceDetailComponent } from "../components/business/CompServiceDetailComponent";

export function PageServiceDetailPage() {
  return (
    <main data-bmv-page-id="PAGE-SERVICE-DETAIL"
      data-bmv-mobile-navigation="contextual"
      data-bmv-mobile-primary-action="sticky"
      data-bmv-mobile-data-presentation="stacked_cards"
      data-bmv-mobile-density="preserve"
    >
      <span data-bmv-acceptance-test-id="TEST-HOME-BROWSE-SERVICES" hidden />
      <span data-bmv-acceptance-test-id="TEST-SERVICE-DETAIL-VIEW" hidden />
      <span data-bmv-acceptance-test-id="TEST-BOOKING-FORM-DISPLAY" hidden />
      <span data-bmv-acceptance-test-id="TEST-BOOKING-CONFIRMATION" hidden />
      {/* BMV_REQUIRED_BC_START */}
      <CompServiceDetailComponent />
      {/* BMV_REQUIRED_BC_END */}
    </main>
  );
}
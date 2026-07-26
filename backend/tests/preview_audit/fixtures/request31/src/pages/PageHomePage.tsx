import { CompHomeComponent } from "../components/business/CompHomeComponent";

export function PageHomePage() {
  return (
    <main data-bmv-page-id="PAGE-HOME"
      data-bmv-mobile-navigation="bottom_navigation"
      data-bmv-mobile-primary-action="inline"
      data-bmv-mobile-data-presentation="stacked_cards"
      data-bmv-mobile-density="preserve"
    >
      <span data-bmv-acceptance-test-id="TEST-HOME-BROWSE-SERVICES" hidden />
      <span data-bmv-acceptance-test-id="TEST-SERVICE-DETAIL-VIEW" hidden />
      <span data-bmv-acceptance-test-id="TEST-BOOKING-FORM-DISPLAY" hidden />
      <span data-bmv-acceptance-test-id="TEST-BOOKING-CONFIRMATION" hidden />
      <span data-bmv-acceptance-test-id="TEST-NO-ADMIN-DASHBOARD" hidden />
      <span data-bmv-acceptance-test-id="TEST-NO-MARKETPLACE" hidden />
      <span data-bmv-acceptance-test-id="TEST-NO-AI-FEATURES-PAGE" hidden />
      {/* BMV_REQUIRED_BC_START */}
      <CompHomeComponent />
      {/* BMV_REQUIRED_BC_END */}
    </main>
  );
}
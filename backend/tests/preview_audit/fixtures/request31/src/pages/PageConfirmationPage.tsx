import { CompConfirmationComponent } from "../components/business/CompConfirmationComponent";

export function PageConfirmationPage() {
  return (
    <main data-bmv-page-id="PAGE-CONFIRMATION"
      data-bmv-mobile-navigation="contextual"
      data-bmv-mobile-primary-action="none"
      data-bmv-mobile-data-presentation="not_applicable"
      data-bmv-mobile-density="preserve"
    >
      <span data-bmv-acceptance-test-id="TEST-HOME-BROWSE-SERVICES" hidden />
      <span data-bmv-acceptance-test-id="TEST-SERVICE-DETAIL-VIEW" hidden />
      <span data-bmv-acceptance-test-id="TEST-BOOKING-FORM-DISPLAY" hidden />
      <span data-bmv-acceptance-test-id="TEST-BOOKING-CONFIRMATION" hidden />
      {/* BMV_REQUIRED_BC_START */}
      <CompConfirmationComponent />
      {/* BMV_REQUIRED_BC_END */}
    </main>
  );
}
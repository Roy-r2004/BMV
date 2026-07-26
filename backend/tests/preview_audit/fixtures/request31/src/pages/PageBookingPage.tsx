import { CompBookingComponent } from "../components/business/CompBookingComponent";

export function PageBookingPage() {
  return (
    <main data-bmv-page-id="PAGE-BOOKING"
      data-bmv-mobile-navigation="contextual"
      data-bmv-mobile-primary-action="sticky"
      data-bmv-mobile-data-presentation="stacked_cards"
      data-bmv-mobile-density="compact"
    >
      <span data-bmv-acceptance-test-id="TEST-HOME-BROWSE-SERVICES" hidden />
      <span data-bmv-acceptance-test-id="TEST-SERVICE-DETAIL-VIEW" hidden />
      <span data-bmv-acceptance-test-id="TEST-BOOKING-FORM-DISPLAY" hidden />
      <span data-bmv-acceptance-test-id="TEST-BOOKING-CONFIRMATION" hidden />
      <span data-bmv-acceptance-test-id="TEST-NO-PAYMENT-FLOW" hidden />
      <span data-bmv-acceptance-test-id="TEST-NO-CUSTOMER-ACCOUNT" hidden />
      {/* BMV_REQUIRED_BC_START */}
      <CompBookingComponent />
      {/* BMV_REQUIRED_BC_END */}
    </main>
  );
}
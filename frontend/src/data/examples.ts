/**
 * The Examples page: one example per kind of business we work with. Each
 * starts from a question an owner brings, shows what a consultation would
 * test and which of the owner's own figures each test uses, and the system it
 * could lead to. They illustrate the method; they are not clients, and they
 * carry no results or figures, because there are none to quote.
 *
 * `screens` name the system's screens. Each is drawn as a panel in the 3D
 * scene, and its name picks the panel's layout (components/concepts/screenTexture).
 */
export interface Example {
  id: string;
  /** The kind of business, as an owner would describe it. */
  business: string;
  /** The owner's question, in their words. It prefills the consultation. */
  question: string;
  /** What the consultation would test, each against a figure the owner has. */
  tests: { claim: string; against: string }[];
  /** The system it could lead to, if the figures say a system is the answer. */
  system: string;
  systemLine: string;
  screens: string[];
  /** What would show whether it worked. */
  measures: string[];
}

export const EXAMPLES: Example[] = [
  {
    id: 'clinic',
    business: 'Clinics',
    question: 'We miss calls in the evening and I think we are losing bookings. Is it worth fixing, and how?',
    tests: [
      { claim: 'Evening calls really are going unanswered, and how many', against: 'your phone log' },
      { claim: 'Missed callers book elsewhere, rather than calling back the next day', against: 'your booking records' },
      { claim: 'The gap is in how calls are handled, not in how many staff are on shift', against: 'your rota' },
    ],
    system: 'An after-hours booking assistant',
    systemLine:
      'Answers calls and messages when the clinic is closed, books routine visits straight into the calendar, and hands anything clinical to staff in the morning.',
    screens: ['Patient chat', 'Booking calendar', 'Intake form builder', 'Morning handover report'],
    measures: ['Calls answered after hours', 'Bookings made from after-hours contacts', 'Cases handed to staff each morning'],
  },
  {
    id: 'restaurant',
    business: 'Restaurants',
    question: 'Our delivery orders keep growing but profit does not. Which dishes and which channels actually make money?',
    tests: [
      { claim: 'Platform commission turns some dishes unprofitable on delivery', against: 'your sales export and price list' },
      { claim: 'Delivery takes kitchen time away from fuller-margin tables', against: 'your order times by hour' },
      { claim: 'Waste rises on the days delivery is busiest', against: 'your stock and waste records' },
    ],
    system: 'A margin and prep dashboard',
    systemLine:
      'Shows the margin of every dish on every channel after commission, and forecasts each day’s prep so less is thrown away.',
    screens: ['Margin dashboard', 'Dish detail', 'Prep forecast', 'Weekly owner report'],
    measures: ['Margin per order, by channel', 'Food thrown away each week', 'Share of orders on the most profitable channel'],
  },
  {
    id: 'retail',
    business: 'Shops',
    question: 'Should I open a second shop, or put the money into selling online?',
    tests: [
      { claim: 'Your customers come from far enough away for a second location to reach new ones', against: 'your customer postcodes' },
      { claim: 'Online demand exists for what you sell at your prices', against: 'your enquiries and best sellers' },
      { claim: 'The business can carry either option until it pays back', against: 'your accounts and cash position' },
    ],
    system: 'An online store linked to the shop’s stock',
    systemLine:
      'One stock count for the shop and the website, a reorder list that follows what sells, and orders from both in one place.',
    screens: ['Online storefront', 'Stock by location dashboard', 'Demand forecast', 'Reorder planner'],
    measures: ['Online sales against the shop’s', 'Items out of stock each week', 'Months until the investment pays back'],
  },
  {
    id: 'studio',
    business: 'Studios and gyms',
    question: 'Members join in January and most have left by March. How do I keep them?',
    tests: [
      { claim: 'Members who leave stop attending weeks before they cancel', against: 'your attendance records' },
      { claim: 'Leavers cluster in particular classes or times', against: 'your class register' },
      { claim: 'Price is not the main reason people leave', against: 'your cancellation reasons and price history' },
    ],
    system: 'A member retention assistant',
    systemLine:
      'Spots members whose attendance is falling, suggests a class that suits their pattern, and sends the message from the studio in its own voice.',
    screens: ['Member insights dashboard', 'Attendance timeline', 'Member chat', 'Class schedule'],
    measures: ['Members still active after three months', 'Members contacted before they cancel', 'Classes with the most leavers'],
  },
  {
    id: 'firm',
    business: 'Professional firms',
    question: 'My team spends hours chasing and checking client documents. What can we safely automate?',
    tests: [
      { claim: 'Most of the time goes on chasing missing documents, not on reviewing them', against: 'your team’s timesheets' },
      { claim: 'The same documents are requested for most clients', against: 'your past engagement checklists' },
      { claim: 'Review steps can be checked by software without changing who signs off', against: 'your current review procedure' },
    ],
    system: 'A client document portal with a review queue',
    systemLine:
      'Clients upload against a checklist that chases them on its own; documents arrive pre-checked, and every sign-off stays with your people.',
    screens: ['Client portal', 'Document checklist builder', 'Review queue', 'Deadline calendar'],
    measures: ['Hours spent chasing documents', 'Days from first request to complete file', 'Files returned for missing items'],
  },
  {
    id: 'logistics',
    business: 'Logistics',
    question: 'Deliveries run late on certain days and I cannot see why.',
    tests: [
      { claim: 'Late days share a pattern of routes, drivers or loading times', against: 'your delivery records' },
      { claim: 'Loading, not driving, is where the time is lost', against: 'your depot timestamps' },
      { claim: 'Routes are planned around last week, not around today’s orders', against: 'your planning sheets' },
    ],
    system: 'A dispatch and route planner',
    systemLine:
      'Plans each day’s routes from that day’s orders, shows where every delivery stands, and records why each late one was late.',
    screens: ['Live delivery map', 'Driver schedule', 'Late delivery report', 'Daily dispatch planner'],
    measures: ['Deliveries on time, by day', 'Minutes lost at loading', 'Late deliveries with a recorded cause'],
  },
  {
    id: 'home-services',
    business: 'Home services',
    question: 'Quotes take me two days to send, and I lose jobs to faster competitors.',
    tests: [
      { claim: 'Jobs are lost when the quote is slow, not when it is high', against: 'your quotes won and lost' },
      { claim: 'Most quotes are built from the same few job types', against: 'your past quotes' },
      { claim: 'Crews have room for more jobs in the weeks you lose them', against: 'your job calendar' },
    ],
    system: 'Same-day quoting and job booking',
    systemLine:
      'Builds a quote from the customer’s photos and answers within the hour, books the job into a crew’s calendar, and keeps the customer informed.',
    screens: ['Quote builder', 'Job calendar', 'Customer chat', 'Crew assignments panel'],
    measures: ['Hours from enquiry to quote', 'Quotes accepted', 'Crew days left empty'],
  },
  {
    id: 'new-venture',
    business: 'New ventures',
    question: 'I want to open a café near offices. Do the numbers work before I sign the lease?',
    tests: [
      { claim: 'Enough people pass at the hours a café earns', against: 'your site visits and counts' },
      { claim: 'The rent leaves a margin at a realistic number of sales', against: 'the lease terms and your menu prices' },
      { claim: 'You can fund the months before the café breaks even', against: 'your budget and savings' },
    ],
    system: 'Often no software at all',
    systemLine:
      'The answer is usually a financial case and an opening roadmap. Software comes later, if the figures show it is needed.',
    screens: ['Financial case report', 'Break-even forecast', 'Opening roadmap timeline', 'Risk review'],
    measures: ['Sales needed each day to break even', 'Months of funding before break-even', 'Rent as a share of sales'],
  },
];

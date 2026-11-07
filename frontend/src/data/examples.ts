/**
 * The Examples page: people who come with an idea first, then businesses
 * already running. Each starts from the question its owner brings, shows
 * what a consultation would test and against which figures, and what we
 * would build. They illustrate the method; they are not clients, and they
 * carry no results or figures, because there are none to quote.
 *
 * An idea has few figures of its own yet, so its tests also use published
 * market figures, labelled as cited. `screens` name the system's screens, as
 * the technical plan would set them out; the Examples page lists them.
 */
export type Stage = 'idea' | 'running';

export const STAGES: { stage: Stage; label: string }[] = [
  { stage: 'idea', label: 'Starting something new' },
  { stage: 'running', label: 'Already running a business' },
];

export interface Example {
  id: string;
  stage: Stage;
  /** What it is, as its owner would say it. */
  business: string;
  /** The owner's question, in their words. It prefills the consultation. */
  question: string;
  /** What the consultation would test, and against which figures. */
  tests: { claim: string; against: string; source: 'theirs' | 'cited' }[];
  /** What we would build, if the figures say a system is the answer. */
  system: string;
  systemLine: string;
  screens: string[];
  /** What would show whether it worked. */
  measures: string[];
}

export const EXAMPLES: Example[] = [
  // ── starting something new ────────────────────────────────────────────
  {
    id: 'booking-app',
    stage: 'idea',
    business: 'A booking app',
    question: 'I have an idea for an app that books home cleaners. Is there a real business in it, and can you build it for me?',
    tests: [
      { claim: 'Enough households in your city pay for cleaning to support an app', against: 'published market figures', source: 'cited' },
      { claim: 'Cleaners would join at the commission you have in mind', against: 'your conversations with cleaners', source: 'theirs' },
      { claim: 'Your budget carries the app until bookings pay for it', against: 'your budget', source: 'theirs' },
    ],
    system: 'The app, designed and built for you',
    systemLine:
      'Booking and payment for customers, a schedule for each cleaner, and an admin panel for you. We build it, launch it and hand it over with the operations manual.',
    screens: ['Booking calendar', 'Customer chat', 'Cleaner schedule', 'Admin panel'],
    measures: ['Bookings each week', 'Cleaners active each week', 'Months until the app covers its costs'],
  },
  {
    id: 'online-store',
    stage: 'idea',
    business: 'An online store',
    question: 'I want to sell my own skincare products online. Where do I start, and what will it cost to launch?',
    tests: [
      { claim: 'Your price leaves a margin after production, delivery and advertising', against: 'your product costs', source: 'theirs' },
      { claim: 'People search for products like yours at your price', against: 'published search and market figures', source: 'cited' },
      { claim: 'Your launch budget covers stock and the first months of advertising', against: 'your budget', source: 'theirs' },
    ],
    system: 'The store, built and launched for you',
    systemLine:
      'The storefront, payments, stock and orders in one place, and an assistant that answers customers’ questions about your products.',
    screens: ['Online storefront', 'Product editor', 'Orders dashboard', 'Customer chat'],
    measures: ['Cost of winning each customer', 'Margin on each order', 'Customers who order again'],
  },
  {
    id: 'ai-service',
    stage: 'idea',
    business: 'An AI service',
    question: 'I want to start an AI tutoring service for school students. Can it work, and can you build the AI?',
    tests: [
      { claim: 'Parents pay for tutoring at prices an AI service can undercut', against: 'published tutoring prices', source: 'cited' },
      { claim: 'The AI can teach your subjects to the standard parents expect', against: 'your syllabus and sample lessons', source: 'theirs' },
      { claim: 'You can reach parents at a cost the subscription covers', against: 'your marketing plan and budget', source: 'theirs' },
    ],
    system: 'The tutoring platform and its AI, built for you',
    systemLine:
      'Lessons and practice set by the AI for each student, progress reports for parents, and your own controls over what the AI may say.',
    screens: ['Student chat', 'Lesson planner', 'Progress dashboard', 'Parent report'],
    measures: ['Students active each week', 'Progress made by each student', 'Parents who renew'],
  },
  {
    id: 'cafe',
    stage: 'idea',
    business: 'A café',
    question: 'I want to open a café near offices. Do the numbers work before I sign the lease?',
    tests: [
      { claim: 'Enough people pass at the hours a café earns', against: 'your site visits and counts', source: 'theirs' },
      { claim: 'The rent leaves a margin at a realistic number of sales', against: 'the lease terms and your menu prices', source: 'theirs' },
      { claim: 'You can fund the months before the café breaks even', against: 'your budget and savings', source: 'theirs' },
    ],
    system: 'The plan first, and software only if it pays',
    systemLine:
      'The answer is usually a financial case and an opening roadmap. When the café needs ordering, a loyalty scheme or a booking system, we build it.',
    screens: ['Financial case report', 'Break-even forecast', 'Opening roadmap timeline', 'Risk review'],
    measures: ['Sales needed each day to break even', 'Months of funding before break-even', 'Rent as a share of sales'],
  },

  // ── already running a business ────────────────────────────────────────
  {
    id: 'clinic',
    stage: 'running',
    business: 'A clinic',
    question: 'We miss calls in the evening and I think we are losing bookings. Is it worth fixing, and how?',
    tests: [
      { claim: 'Evening calls really are going unanswered, and how many', against: 'your phone log', source: 'theirs' },
      { claim: 'Missed callers book elsewhere, rather than calling back the next day', against: 'your booking records', source: 'theirs' },
      { claim: 'The gap is in how calls are handled, not in how many staff are on shift', against: 'your rota', source: 'theirs' },
    ],
    system: 'An after-hours booking assistant',
    systemLine:
      'Answers calls and messages when the clinic is closed, books routine visits straight into the calendar, and hands anything clinical to staff in the morning.',
    screens: ['Patient chat', 'Booking calendar', 'Intake form builder', 'Morning handover report'],
    measures: ['Calls answered after hours', 'Bookings made from after-hours contacts', 'Cases handed to staff each morning'],
  },
  {
    id: 'restaurant',
    stage: 'running',
    business: 'A restaurant',
    question: 'Our delivery orders keep growing but profit does not. Which dishes and which channels actually make money?',
    tests: [
      { claim: 'Platform commission turns some dishes unprofitable on delivery', against: 'your sales export and price list', source: 'theirs' },
      { claim: 'Delivery takes kitchen time away from fuller-margin tables', against: 'your order times by hour', source: 'theirs' },
      { claim: 'Waste rises on the days delivery is busiest', against: 'your stock and waste records', source: 'theirs' },
    ],
    system: 'A margin and prep dashboard',
    systemLine:
      'Shows the margin of every dish on every channel after commission, and forecasts each day’s prep so less is thrown away.',
    screens: ['Margin dashboard', 'Dish detail', 'Prep forecast', 'Weekly owner report'],
    measures: ['Margin per order, by channel', 'Food thrown away each week', 'Share of orders on the most profitable channel'],
  },
  {
    id: 'shop',
    stage: 'running',
    business: 'A shop',
    question: 'Should I open a second shop, or put the money into selling online?',
    tests: [
      { claim: 'Your customers come from far enough away for a second location to reach new ones', against: 'your customer postcodes', source: 'theirs' },
      { claim: 'Online demand exists for what you sell at your prices', against: 'your enquiries and best sellers', source: 'theirs' },
      { claim: 'The business can carry either option until it pays back', against: 'your accounts and cash position', source: 'theirs' },
    ],
    system: 'An online store linked to the shop’s stock',
    systemLine:
      'One stock count for the shop and the website, a reorder list that follows what sells, and orders from both in one place.',
    screens: ['Online storefront', 'Stock by location dashboard', 'Demand forecast', 'Reorder planner'],
    measures: ['Online sales against the shop’s', 'Items out of stock each week', 'Months until the investment pays back'],
  },
  {
    id: 'firm',
    stage: 'running',
    business: 'A professional firm',
    question: 'My team spends hours chasing and checking client documents. What can we safely automate?',
    tests: [
      { claim: 'Most of the time goes on chasing missing documents, not on reviewing them', against: 'your team’s timesheets', source: 'theirs' },
      { claim: 'The same documents are requested for most clients', against: 'your past engagement checklists', source: 'theirs' },
      { claim: 'Review steps can be checked by software without changing who signs off', against: 'your current review procedure', source: 'theirs' },
    ],
    system: 'A client document portal with a review queue',
    systemLine:
      'Clients upload against a checklist that chases them on its own; documents arrive pre-checked, and every sign-off stays with your people.',
    screens: ['Client portal', 'Document checklist builder', 'Review queue', 'Deadline calendar'],
    measures: ['Hours spent chasing documents', 'Days from first request to complete file', 'Files returned for missing items'],
  },
];

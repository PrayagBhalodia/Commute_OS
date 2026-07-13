export const DEMO_USER_ID = "user-demo";

export const DEMO_PROMPT =
  "I have an interview tomorrow at Jio Institute in Navi Mumbai. I am travelling from Ahmedabad with one suitcase. I need to arrive one hour early and return the same evening. Prioritize reliability and time.";

export const PROMPT_SUGGESTIONS = [
  DEMO_PROMPT,
  "Plan a low-cost round trip from Mumbai to Pune tomorrow morning.",
  "I need to reach Mumbai Airport from Navi Mumbai with two bags by 6 PM.",
  "Find the most comfortable route from Delhi to Bengaluru next week.",
];

export const ASSISTANT_GREETINGS = [
  "Where are you off to?",
  "Where are you headed?",
  "What is your next stop?",
  "How may I assist you with your journey today?",
];

export const DEFAULT_PLAN_FORM = {
  user_id: DEMO_USER_ID,
  goal_text: DEMO_PROMPT,
  origin: "Ahmedabad",
  destination: "Jio Institute",
  return_required: true,
  luggage_count: 1,
  required_buffer_minutes: 60,
  max_options: 3,
};

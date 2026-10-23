## Overview

The Next.js frontend for the telco. voice and chat agent, built on LiveKit's [JavaScript SDK](https://github.com/livekit/client-sdk-js) and [React Components](https://github.com/livekit/components-js). It started from the `agent-starter-react` template and now has three surfaces:

- `/` persona picker, then the customer portal at `/portal` (overview, packages, recharge, offers, support, and the assistant page with its chat bubble and notification bell).
- `/login` then `/dashboard`: the admin portal (control center, subscribers, transactions, support cases, network incidents, AI monitor, offers, chatbot, knowledge, conversations, listen).
- `/chat`: the standalone full-screen voice/chat widget, which keeps the original LiveKit starter look.

The app implements its own token server (`/api/token` for customers with a portal session, `/api/listen-token` for admins). Both only join an existing room.

## Running locally

Set `LIVEKIT_URL` in `.env.local` to a reachable LiveKit server, then run the backend, the agent worker and `pnpm dev` as described in the repository README. Design tokens and patterns: [DESIGN.md](DESIGN.md).

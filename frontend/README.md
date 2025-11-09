## CloudIoT Frontend

A Next.js 14 + Tailwind CSS dashboard for interacting with the CloudIoT infrastructure.

### Features

- Bright plant-themed landing page that surfaces each plant with live vitals.
- Plant detail view with Recharts time-series visuals and a simulated control panel (lights, pump, fan).
- Axios-powered data layer that talks to the FastAPI endpoints (`/plants`, `/plants/{id}`, `/plants/{id}/timeseries`).
- All control buttons are optimistic stubs and can later be wired to real actuators or IoT topics.

### Prerequisites

- Node.js 18+
- npm (bundled with Node) or pnpm/yarn if preferred

### Setup

```bash
cd frontend
npm install
```

Create a `.env.local` file and point the app at the API Gateway deployed by CDK:

```
NEXT_PUBLIC_API_BASE_URL=https://your-api-id.execute-api.your-region.amazonaws.com
# Optional: talk to a locally running FastAPI dev server
NEXT_PUBLIC_LOCAL_API_BASE_URL=http://localhost:8000
# Switch between live/mocked data (`true` = always mock, `false` = force real API)
NEXT_PUBLIC_USE_MOCK_API=true
```

### Development

```bash
npm run dev
```

The application will be available at `http://localhost:3000`. Tailwind JIT recompiles automatically.

> Leave `NEXT_PUBLIC_API_BASE_URL` blank (or set `NEXT_PUBLIC_USE_MOCK_API=true`) to explore the cartoon greenhouse with mock data. Set `NEXT_PUBLIC_USE_MOCK_API=false` to force requests against the local/real API.

### Production Build

```bash
npm run build
npm start
```

### Linting & Formatting

```bash
npm run lint
npm run format
```


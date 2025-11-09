## CloudIoT Frontend

A Next.js 14 + Tailwind CSS dashboard for interacting with the CloudIoT infrastructure.

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
```

### Development

```bash
npm run dev
```

The application will be available at `http://localhost:3000`. Tailwind JIT recompiles automatically.

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


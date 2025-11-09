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

Create a `.env.local` file with the following variable and adjust the value to your API Gateway endpoint:

```
NEXT_PUBLIC_API_BASE_URL=https://abc123.execute-api.ap-southeast-1.amazonaws.com
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


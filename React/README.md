# React Week 2 — Senior Engineer Study Notes

## JavaScript Foundations

### Closures

A function remembers variables from the scope where it was **created**, not where it's called.

```js
function makeCounter() {
  let count = 0;
  return function() {
    count++;
    return count;
  }
}

const counter = makeCounter();
counter(); // 1
counter(); // 2 — same count, not reset
```

**Key insight:** `makeAdder(5)` locks `x = 5` in a closure. Any function returned from it carries that value permanently.

```js
function makeAdder(x) {
  return function(y) { return x + y; }
}
const add5 = makeAdder(5);
add5(3); // 8 — x=5 locked, y=3 fresh
```

---

### Promises & Async/Await

**Promise** = object representing a future value. States: `pending → fulfilled | rejected`.

```
Mental model — Pizza delivery:
Order pizza (fetch call)
Restaurant gives receipt (Promise object) ← immediate
You don't stand frozen at door waiting
You watch TV (.then callback registered)
Pizza arrives → doorbell rings → you eat (callback runs)
```

`fetch` is **always** async — never freezes. Real blocking looks like:
```js
while (i < 1000000000) i++; // this actually freezes the browser
```

**Writing a custom Promise:**
```js
function wait(seconds) {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      if (seconds < 10) resolve("done");
      else reject("too long!");
    }, seconds * 1000);
  });
}
```

**Sequential vs Parallel:**
```js
// Sequential — 5 seconds total
const a = await wait(2);
const b = await wait(3);

// Parallel — 3 seconds total (like Python's asyncio.gather)
const [a, b] = await Promise.all([wait(2), wait(3)]);
```

**useEffect async pattern — the right way:**
```js
// WRONG — async useEffect leaks
useEffect(async () => { ... }, []);

// RIGHT
useEffect(() => {
  async function load() { ... }
  load();
}, []);
```

---

### Event Loop

```
JS Runtime:
┌─────────────┐
│ Call Stack  │  ← sync code, one at a time
├─────────────┤
│ Microtasks  │  ← Promise .then, await continuations
├─────────────┤
│ Macrotasks  │  ← setTimeout, setInterval, DOM events
└─────────────┘

Rule: Stack drains → ALL microtasks → ONE macrotask → repeat
```

```js
console.log("1");
setTimeout(() => console.log("2"), 0); // macrotask
Promise.resolve().then(() => console.log("3")); // microtask
console.log("4");
// Output: 1 → 4 → 3 → 2
```

```js
async function run() {
  console.log("A");
  await Promise.resolve(); // goes to microtask queue
  console.log("B");
}
console.log("X");
run();
console.log("Y");
// Output: X → A → Y → B
```

`setTimeout(0)` still runs after microtasks. Zero delay = "ASAP in macrotask queue" — not actually immediate.

---

### Reference Equality

**Primitives** — compared by value. **Objects/Arrays/Functions** — compared by memory address.

```js
5 === 5           // true
{} === {}         // false — different memory addresses
[] === []         // false

const a = { x: 1 };
const b = a;
a === b           // true — same address
```

React uses `===` to check if props changed. This is why `useMemo`/`useCallback`/`memo` exist.

---

### ESM Modules

```js
export function add(a, b) { return a + b; } // named
export default function App() { ... }        // default

import App from './App';           // default
import { add } from './utils';     // named
import * as utils from './utils';  // namespace
```

ESM = static. Imports resolved before code runs. Enables tree shaking. Always use ESM in React projects — CommonJS (`require`) can't be tree-shaken.

---

## React Rendering Model

**"Render" = React calls your function.** That's it.

**What triggers a render:**
1. `useState` setter called
2. `useReducer` dispatch called
3. Parent re-renders → child re-renders (by default)

**What does NOT trigger render:**
```js
let count = 0; count = 5;      // invisible to React
const ref = useRef(0); ref.current = 5; // no render
```

**Render ≠ DOM update:**
```
Render phase  → React calls your fn, builds JSX tree
Commit phase  → React diffs old/new tree, updates DOM minimally
```

---

## Batching

React 18 batches ALL state updates → one render, regardless of where they are.

```js
function handleClick() {
  setA(1); // doesn't render yet
  setB(2); // doesn't render yet
} // renders ONCE here
```

Pre-React 18: only batched inside React event handlers. React 18: batches everywhere including `setTimeout`, Promises.

**Force immediate render with `flushSync`:**
```js
import { flushSync } from 'react-dom';
flushSync(() => setA(1)); // renders NOW
flushSync(() => setB(2)); // renders NOW — 2 total renders
```

---

## Fiber & Reconciliation

Fiber = React's internal data structure. Every component = one Fiber node (JS object with `type`, `child`, `sibling`, `return`, `memoizedState`, `alternate`).

**Two trees always exist:**
- Current tree — what's on screen
- Work-in-progress tree — what's being built

**Diffing rules:**
- Same type → reuse node, update props
- Different type → destroy old, create new
- Gone → destroy

```js
// isLoggedIn flips false → true
{isLoggedIn ? <Dashboard /> : <Login />}
// Login DESTROYED entirely. Dashboard CREATED fresh.
// Login's DOM and state = gone.
```

**Never define components inside components:**
```js
function Parent() {
  function Child() { ... } // new function ref every render = different type
  return <Child />;        // Child destroyed + recreated every render, state wiped
}
```

**Key prop:**
```js
// NEVER use index as key for dynamic lists
items.map((item, index) => <li key={index}>{item}</li>) // reorder = wrong matches

// Use stable unique ID
items.map(item => <li key={item.id}>{item.name}</li>)
```

**Two phases:**
```
Render phase  (interruptible) → diff trees, mark changes, no side effects
Commit phase  (synchronous)   → apply changes to DOM, can't interrupt
```

---

## Concurrent Features

### useTransition
```js
const [isPending, startTransition] = useTransition();

startTransition(() => {
  setResults(filterData(query)); // non-urgent — can interrupt
});
// input stays responsive while heavy filter runs
```

### Suspense
Component "throws" a Promise when not ready. Suspense catches it, shows fallback.

```js
// Code splitting
const Dashboard = lazy(() => import('./Dashboard'));

<Suspense fallback={<Spinner />}>
  <Dashboard />
</Suspense>

// Data fetching (React Query)
function UserProfile() {
  const { data } = useSuspenseQuery({ queryKey: ['user'], queryFn: fetchUser });
  return <div>{data.name}</div>; // data GUARANTEED — no loading check needed
}
```

**useTransition + Suspense together = old content stays visible during transition instead of blank screen.**

---

## memo, useMemo, useCallback

### memo
```js
const Child = memo(function Child({ name }) { ... });
// Only re-renders if props change (via ===)
```

### useMemo
```js
const filteredPosts = useMemo(
  () => filterPosts(POST_DATA, filter), // expensive computation cached
  [filter] // recompute only when filter changes
);
```

### useCallback
```js
const handleClick = useCallback(() => {
  console.log("clicked");
}, []); // stable function reference
```

**useCallback is syntactic sugar:**
```js
// These are identical:
const fn = useCallback(() => doSomething(), []);
const fn = useMemo(() => () => doSomething(), []);
```

**The trio working together:**
```
memo on component + useMemo/useCallback on props = actually skip re-renders
memo alone + object/array/function props        = false security, still re-renders
```

| Prop type | Fix |
|---|---|
| Primitive | nothing needed |
| Object/Array | `useMemo` |
| Function | `useCallback` |

**Don't prematurely optimize.** No perf problem → no memo. Measure first, optimize second. `memo` has cost: memory, comparison on every render, code complexity.

**Real-world example:** ProfilePage with 1000 posts:
- Toggle theme → `filteredPosts` same ref (filter unchanged) → `memo` on PostList skips render
- Type in filter → `filteredPosts` recomputed → PostList re-renders with new data

---

## useEffect — Synchronization Mental Model

```
❌ Wrong: "run on mount, update, unmount"
✓ Right:  "synchronize something outside React with current state/props"
```

"Outside React" = fetch, DOM, websockets, localStorage, timers.

**Dependency array:**
```js
useEffect(() => { ... });           // runs after EVERY render
useEffect(() => { ... }, []);       // runs once after first render
useEffect(() => { ... }, [userId]); // runs when userId changes
```

**Stale closure bug:**
```js
useEffect(() => {
  const id = setInterval(() => {
    console.log(count); // captures count=0 from first render, always 0
  }, 1000);
  return () => clearInterval(id);
}, []); // empty deps — stale closure
```

**Fix with functional update (no dep needed):**
```js
useEffect(() => {
  const id = setInterval(() => {
    setCount(c => c + 1); // React gives latest value, no closure needed
  }, 1000);
  return () => clearInterval(id);
}, []);
```

**Race condition + fix:**
```js
useEffect(() => {
  let cancelled = false;

  fetch(`/api/user/${userId}`)
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .then(data => {
      if (!cancelled) setUser(data); // guard stale responses
    })
    .catch(err => {
      if (!cancelled) setError(err); // always handle errors
    });

  return () => { cancelled = true }; // cleanup on userId change
}, [userId]);
```

**Why `fetch` doesn't throw on 404/500:**
```js
const res = await fetch('/api');
// res.ok = false if 404/500 — but NO throw
if (!res.ok) throw new Error(`HTTP ${res.status}`); // must check manually
```

**This is why React Query exists** — race conditions, error handling, loading states, HTTP checks all automatic.

---

## Context

**Prop drilling problem → Context solution:**
```js
const ThemeContext = createContext('light');

function App() {
  const [theme, setTheme] = useState('dark');
  return (
    <ThemeContext.Provider value={theme}>
      <Page /> {/* no prop needed */}
    </ThemeContext.Provider>
  );
}

function Button() {
  const theme = useContext(ThemeContext); // grabs from nearest Provider
  return <button className={theme}>click</button>;
}
```

**Why context causes re-renders:**
```js
// BAD — new object every render → ALL consumers re-render
<ThemeContext.Provider value={{ theme, user }}>

// FIX 1 — split contexts (best)
<ThemeContext.Provider value={theme}>      // primitive
  <UserContext.Provider value={user}>

// FIX 2 — memoize value
const value = useMemo(() => ({ theme, user }), [theme, user]);
```

**Real-world gotcha:** `notifications` updating every second in shared context → `Navbar` (which only uses `user`) re-renders every second. Fix: split into `AuthContext` and `NotificationContext`.

**Rule: One context = one concern. Unrelated state = separate contexts.**

**Context vs React Query vs useState:**
```
useState    — local UI state (open/closed, input value)
Context     — global UI state (theme, language, auth user)
React Query — server state (anything from API)
```

Don't put server data in Context — no caching, no invalidation, no background refetch.

---

## React Query

**Server state problems it solves:**
```
When is cache stale? When to refetch? Multiple components same data?
User leaves tab, comes back — fresh? Two mutations in flight — which wins?
```

**Cache = queryKey → data:**
```js
useQuery({ queryKey: ['user', 1], queryFn: fetchUser }) // Component A
useQuery({ queryKey: ['user', 1], queryFn: fetchUser }) // Component B
// One fetch. Both get same data.
```

**Data lifecycle:**
```
fresh → stale → inactive → deleted

staleTime  — how long data stays fresh (default: 0ms)
gcTime     — how long inactive data kept in cache (default: 5min)
```

**isLoading vs isFetching:**
```js
isLoading  = no data + fetching → show skeleton
isFetching = has data + fetching → show subtle spinner
```

**Background refetching:** stale data shown immediately, fresh data fetched in background, UI updates seamlessly.

**Refetch triggers:** component mount, window focus, network reconnect, manual invalidation, polling interval.

**Optimistic updates:**
```js
onMutate: async (newData) => {
  await queryClient.cancelQueries({ queryKey }); // 1. kill stale refetches
  const previous = queryClient.getQueryData(queryKey); // 2. snapshot for rollback
  queryClient.setQueryData(queryKey, newData); // 3. optimistic update
  return { previous };
},
onError: (err, data, context) => {
  queryClient.setQueryData(queryKey, context.previous); // rollback
},
onSettled: () => {
  queryClient.invalidateQueries({ queryKey }); // sync with server
}
```

**Why `cancelQueries` before optimistic update:** without it, an in-flight background refetch could resolve after the optimistic update and overwrite it with stale server data.

**Why `invalidateQueries` on `onSettled`:** optimistic = temporary. Server = source of truth. Refetch syncs real state. If optimistic update keeps reverting → check if API is actually saving changes.

**React Query vs Redux:**
```
Server state (API data)        → React Query replaces Redux
Global UI state (theme, auth)  → Context often enough; Redux for complex cases
```

---

## Vite Internals

**Old bundlers (Webpack):** bundle everything before dev server starts → slow cold start, slow HMR.

**Vite dev server:** no bundling. Browser does module graph resolution. Vite transforms individual files on demand.

```
Browser requests localhost:5173
→ Vite serves index.html
→ Browser sees <script type="module">
→ Browser requests each import
→ Vite transforms + serves on demand
→ Cold start = instant
```

**Two tools inside Vite:**
```
Dev:  esbuild  (Go-based, 10-100x faster) — transforms TS/JSX, no full bundling
Prod: Rollup   — tree shaking, chunk splitting, optimized output
```

**HMR:** file changes → Vite retransforms that file only → WebSocket message to browser → browser replaces module → React Fast Refresh re-renders affected components. State preserved.

**Dependency pre-bundling:** node_modules (CJS) pre-converted to ESM, merged into fewer files. Cached in `node_modules/.vite/deps`.

**Environment variables:**
```js
// Only VITE_ prefix exposed to browser
VITE_API_URL=http://localhost:8000  // visible in browser bundle
SECRET_KEY=private                   // undefined in browser

import.meta.env.VITE_API_URL  // use in React code (not process.env)
import.meta.env.MODE           // "development" or "production"
import.meta.env.DEV            // true in dev
```

**File priority (highest → lowest):**
```
.env.development.local
.env.development
.env.local
.env
```

`npm run dev` → loads `.env.development`. `npm run build` → loads `.env.production`.

**Never commit `.env.local` or `.env.*.local`. Real secrets → server environment variables, never in files.**

**Path aliases:**
```js
// vite.config.ts
resolve: { alias: { "@": path.resolve(__dirname, "./src") } }

// tsconfig.json — TS needs to know too
{ "paths": { "@/*": ["src/*"] } }

// Usage
import Button from "@/components/Button"; // instead of ../../components/Button
```

---

## TypeScript with React

### Typing Props
```tsx
type ButtonProps = {
  label: string;
  onClick: () => void;
  disabled?: boolean;         // optional
  children: React.ReactNode;  // anything React can render
}
```

### Typing Hooks
```tsx
const [user, setUser] = useState<User | null>(null);    // explicit when needed
const inputRef = useRef<HTMLInputElement>(null);          // DOM ref — can be null
const countRef = useRef<number>(0);                       // mutable value — not null
```

### Generics in Components
```tsx
type ListProps<T> = {
  items: T[];
  renderItem: (item: T) => React.ReactNode;
}

function List<T>({ items, renderItem }: ListProps<T>) {
  return <ul>{items.map((item, i) => <li key={i}>{renderItem(item)}</li>)}</ul>;
}
// T inferred automatically from usage
```

### Discriminated Unions
```tsx
// BAD — all optional, no safety
type Props = { variant: 'link' | 'button'; href?: string; onClick?: () => void; }

// GOOD — impossible states unrepresentable
type Props =
  | { variant: 'link'; href: string }
  | { variant: 'button'; onClick: () => void }

// Async state pattern
type AsyncState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T }   // data only exists in success
  | { status: 'error'; error: Error } // error only exists in error

// TS knows data exists — no optional chaining needed
if (state.status === 'success') return <div>{state.data.name}</div>;
```

### Typing Events
```tsx
function handleChange(e: React.ChangeEvent<HTMLInputElement>) { ... }
function handleSubmit(e: React.FormEvent<HTMLFormElement>) { e.preventDefault(); }
// Or let TS infer inline: <input onChange={e => ...} /> — e inferred automatically
```

---

## Practical Patterns Built

### Custom Hook — useFetch
```ts
function useFetch<T>(url: string) {
  const [state, setState] = useState<AsyncState<T>>({ status: "idle" });

  useEffect(() => {
    if (!url) return;
    let cancelled = false;
    setState({ status: "loading" });

    fetch(url)
      .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); })
      .then(data => { if (!cancelled) setState({ status: "success", data }); })
      .catch(err => { if (!cancelled) setState({ status: "error", error: err }); });

    return () => { cancelled = true; };
  }, [url]);

  return state;
}
```

### Compound Component Pattern — Tabs
- Root component holds state + provides context
- Subcomponents consume context via `useContext`
- Custom hook with guard: `if (!ctx) throw new Error("must be inside <Tabs>")`
- Attach subcomponents: `Tabs.List = List; Tabs.Tab = Tab`
- Why throw not return null: immediate, clear error message pointing to exact problem

### Full Data Fetching Layer — QueryWrapper
```tsx
// Four states — all distinct:
loading → skeleton (data not fetched yet)
error   → error + retry (something broke)
empty   → "No items yet" (fetched successfully, nothing there)
success → actual content
```

Empty ≠ error. Blank screen with no feedback = user thinks app broken.

### Controlled Form
```
onBlur   → validate field when user leaves it (first exposure)
onChange → revalidate if already touched (live feedback)
onSubmit → validate all fields, block if errors

touched state → prevents errors showing before user interacts
```

**Stale state bug:**
```js
const updated = { ...fields, [name]: value };
setFields(updated);
validate(updated); // RIGHT — validate new value
validate(fields);  // WRONG — fields not updated yet (async setState)
```

### Code Splitting
```js
const Dashboard = lazy(() => import('./Dashboard'));
// chunk downloaded only when Dashboard first renders
// second render = cached, instant
```

**Production must-have — Error Boundary around Suspense:**
Deploy new version → old chunks 404 → Error Boundary catches → shows reload button.

### Vite Config
```ts
// vite.config.ts
export default defineConfig({
  plugins: [react(), visualizer({ open: true })],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  build: {
    rollupOptions: {
      output: { manualChunks: { vendor: ['react', 'react-dom'] } }
    }
  }
});
```

---

## Senior-Level Rules

```
1. memo + useMemo/useCallback = pair them, one without other often useless
2. Don't prematurely optimize — measure first, optimize second
3. useEffect = synchronization, not lifecycle
4. Always handle: race conditions, error states, empty states
5. fetch doesn't throw on 404/500 — always check res.ok
6. Discriminated unions > optional props
7. One context = one concern
8. Server state → React Query. UI state → useState/Context
9. Never put secrets in VITE_ env vars
10. Always cancel in-flight requests on cleanup
```
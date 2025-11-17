import { fromHono } from "chanfana";
import { Hono } from "hono";
import { TaskCreate } from "./endpoints/taskCreate";
import { TaskDelete } from "./endpoints/taskDelete";
import { TaskFetch } from "./endpoints/taskFetch";
import { TaskList } from "./endpoints/taskList";
import { DebugStatus } from "./endpoints/debugStatus";
import { MemberStatus } from "./endpoints/memberStatus";
import { MemberActivate } from "./endpoints/memberActivate";
import { GenerateName } from "./endpoints/generateName";

// Start a Hono app
const app = new Hono<{ Bindings: Env }>();

app.options("*", (c) => {
  const allowed = c.env?.ALLOWED_ORIGIN || "*";
  const origin = c.req.header("origin") || "*";
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": allowed === "*" ? origin : allowed,
      "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Member",
      "Access-Control-Max-Age": "86400",
    },
  });
});

app.use("*", async (c, next) => {
  await next();
  const allowed = c.env?.ALLOWED_ORIGIN || "*";
  const origin = c.req.header("origin") || "*";
  c.header("Access-Control-Allow-Origin", allowed === "*" ? origin : allowed);
  c.header("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  c.header("Access-Control-Allow-Headers", "Content-Type,Authorization,X-Member");
  c.header("Access-Control-Allow-Credentials", "true");
});

// Setup OpenAPI registry
const openapi = fromHono(app, {
	docs_url: "/",
});

// Register OpenAPI endpoints
openapi.get("/api/tasks", TaskList);
openapi.post("/api/tasks", TaskCreate);
openapi.get("/api/tasks/:taskSlug", TaskFetch);
openapi.delete("/api/tasks/:taskSlug", TaskDelete);

openapi.get("/api/debug/status", DebugStatus);
openapi.get("/api/member/status", MemberStatus);
openapi.post("/api/member/activate", MemberActivate);
openapi.post("/api/generate", GenerateName);
openapi.post("/api/zhipu/generate", GenerateName);

// You may also register routes for non OpenAPI directly on Hono
// app.get('/test', (c) => c.text('Hono!'))

// Export the Hono app
export default app;

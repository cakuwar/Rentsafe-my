// Express app wiring: middleware + routes.
// Kept separate from server.js so it can be imported directly in tests.
//
import cors from "cors";
import express from "express";
import helmet from "helmet";
import morgan from "morgan";
import swaggerUi from "swagger-ui-express";
import { config } from "./config/index.js";
import { openapiSpec } from "./docs/openapi.js";
import { rateLimiter } from "./middleware/rateLimiter.js";
import healthRoutes from "./routes/health.routes.js";
import analyzeRoutes from "./routes/analyze.routes.js";
import searchRoutes from "./routes/search.routes.js";
import priceRoutes from "./routes/price.routes.js";
import { errorHandler } from "./middleware/errorHandler.js";

const app = express();

app.use(helmet());
app.use(cors({ origin: config.frontendOrigin }));
app.use(morgan("dev"));
app.use(express.json({ limit: "1mb" }));

// Swagger UI, before the rate limiter: one page load fetches several assets,
// and a few reloads should not use up the budget meant for API calls.
// helmet's default CSP upgrades every asset request to https, which breaks
// the page on plain-http localhost, so that one directive is dropped here.
app.get("/", (req, res) => res.redirect("/api/docs"));
app.use(
	"/api/docs",
	helmet({ contentSecurityPolicy: { directives: { upgradeInsecureRequests: null } } }),
	swaggerUi.serve,
	swaggerUi.setup(openapiSpec, { customSiteTitle: "RentSafe MY API" }),
);

app.use(rateLimiter);
app.use("/api/health", healthRoutes);
app.use("/api/analyze", analyzeRoutes);
app.use("/api/search", searchRoutes);
app.use("/api/price", priceRoutes);

app.use((req, res) => {
	res.status(404).json({ error: "Route not found" });
});

app.use(errorHandler);

export default app;

// BullMQ job queue (FYP2). Use this to run the NLP classification
// asynchronously if request latency becomes a problem under load.
// For FYP1 the pipeline can run synchronously; wire this in later.
import { Queue, Worker } from "bullmq";
import { config } from "../config/index.js";

// TODO(FYP2): define the `analysisQueue` (new Queue("analysis", { connection }))
// and a `startWorker(processor)` helper that returns a new Worker for it.
// Then move runAnalysisPipeline's work into the worker for async processing.

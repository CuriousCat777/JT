import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema.js";

const connectionString = process.env.DATABASE_URL;

if (!connectionString) {
  console.warn(
    "DATABASE_URL not set. Database operations will fail until configured."
  );
}

const client = postgres(connectionString ?? "postgres://localhost:5432/greg", {
  max: 10,
  idle_timeout: 20,
  connect_timeout: 10,
});

export const db = drizzle(client, { schema });

export { schema };

export type Database = typeof db;

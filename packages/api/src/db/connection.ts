import Database from "better-sqlite3";
import { migrate } from "./migrate.js";

const DB_PATH = process.env.GITSPOKE_DB_PATH ?? "gitspoke.db";

let db: Database.Database | null = null;

export function getDb(): Database.Database {
  if (!db) {
    db = migrate(DB_PATH);
  }
  return db;
}

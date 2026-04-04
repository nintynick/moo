import Database from "better-sqlite3";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

const DB_PATH = process.env.GITSPOKE_DB_PATH ?? "gitspoke.db";

export function migrate(dbPath: string = DB_PATH): Database.Database {
  const db = new Database(dbPath);
  const schema = readFileSync(join(__dirname, "schema.sql"), "utf-8");
  db.exec(schema);
  console.log(`Database migrated: ${dbPath}`);
  return db;
}

// Run directly
if (process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/.*\//, ""))) {
  migrate();
}

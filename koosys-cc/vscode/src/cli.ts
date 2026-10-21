// Command-line runner for the built-in KooSys text checks: prints findings as JSON.
// Used by tests/score.py and CI. Usage: node out/cli.js <file.c|file.h> ...
import * as fs from "fs";
import { checkText } from "./textchecks";

const findings = process.argv.slice(2).flatMap((f) => checkText(f, fs.readFileSync(f, "utf8")));
process.stdout.write(JSON.stringify(findings) + "\n");

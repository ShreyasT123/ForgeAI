import test from "ava";
import { discoverProject } from "../../source/utils/discovery.js";
import path from "node:path";
import fs from "node:fs";

import { getSettings } from "../../source/utils/config.js";

test("discoverProject finds package info", async (t) => {
  const s = getSettings();
  console.log(`Settings root: ${s.workspace.root}`);
  console.log(`Test CWD: ${process.cwd()}`);
  const summary = await discoverProject();
  t.is(summary.name, "helius-cli");
  t.truthy(summary.mainTech.includes("typescript"));
  t.truthy(summary.structure.includes("source"));
});

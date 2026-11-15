import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { prepareTtsText } from "../lib/ttsText.ts";

describe("prepareTtsText", () => {
  it("replaces DELNO with Russian brand name", () => {
    assert.equal(prepareTtsText("Что умеет DELNO?"), "Что умеет дельно?");
    assert.equal(prepareTtsText("Delno отвечает"), "дельно отвечает");
  });
});

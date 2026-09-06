import { validateRecipe } from "../src/jobs";
import corpusData from "../../../tests/fixtures/hybrid_recipe_corpus.json";
import { describe, expect, it } from "vitest";

type CorpusCase = {
  name: string;
  valid: boolean;
  recipe: Record<string, unknown>;
  expect?: { task: string; device: string; preset: string; modVersion: string; release: string };
};

const corpus = corpusData as CorpusCase[];

describe("shared recipe corpus", () => {
  for (const item of corpus) {
    it(`${item.name} matches the shared contract`, () => {
      if (!item.valid) {
        expect(() => validateRecipe(structuredClone(item.recipe))).toThrow();
        return;
      }
      const normalized = validateRecipe(structuredClone(item.recipe));
      const build = normalized.build as Record<string, unknown>;
      expect({
        task: normalized.task,
        device: normalized.device,
        preset: build.preset,
        modVersion: build.modVersion,
        release: build.modReleaseVersion ?? "V6.0"
      }).toEqual(item.expect);
    });
  }
});

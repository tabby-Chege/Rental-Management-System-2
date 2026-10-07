import assert from "node:assert/strict";
import test from "node:test";
import { filterByLocation, filterProperties } from "./propertySearch.js";

const properties = [
  {
    name: "Cedar Court",
    address: "10 Cedar Street",
    city: "Austin",
    state: "TX",
    zip: "78701",
    yearBuilt: 2022,
    squareFootage: 720,
  },
  {
    name: "Lake House",
    address: "20 Lake Road",
    city: "Denver",
    state: "CO",
    zip: "80202",
    yearBuilt: 2000,
    squareFootage: 1200,
  },
  {
    name: "Unknown Records",
    address: "30 Main Street",
    city: "Austin",
    state: "TX",
    zip: "78702",
    yearBuilt: null,
    squareFootage: null,
  },
];

test("search matches address, city, state, and ZIP without case sensitivity", () => {
  assert.deepEqual(filterProperties(properties, { query: "78701" }), [properties[0]]);
  assert.deepEqual(filterProperties(properties, { query: "DENVER" }), [properties[1]]);
});

test("age filters exclude unknown build years and respect age bands", () => {
  assert.deepEqual(
    filterProperties(properties, { ageFilter: "new", currentYear: 2026 }),
    [properties[0]]
  );
  assert.deepEqual(
    filterProperties(properties, { ageFilter: "old", currentYear: 2026 }),
    [properties[1]]
  );
});

test("size filters exclude missing sizes", () => {
  assert.deepEqual(filterProperties(properties, { sizeFilter: "small" }), [properties[0]]);
  assert.deepEqual(filterProperties(properties, { sizeFilter: "medium" }), [properties[1]]);
});

test("sorting puts known values first without mutating the input", () => {
  const sorted = filterProperties(properties, { sortBy: "newest" });
  assert.deepEqual(sorted, [properties[0], properties[1], properties[2]]);
  assert.deepEqual(properties, [properties[0], properties[1], properties[2]]);
});

test("mock location filtering returns only the selected city's records", () => {
  assert.deepEqual(filterByLocation(properties, "austin", "tx"), [
    properties[0],
    properties[2],
  ]);
  assert.deepEqual(filterByLocation(properties, "Austin", "TX", 1), [properties[0]]);
});
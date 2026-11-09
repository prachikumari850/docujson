import test from "node:test";
import assert from "node:assert/strict";
import { addSelectedFiles, changeFileRole, removeSelectedFile, validateFileRoles } from "./fileSelection.js";
import { createUploadFormData } from "./uploadFormData.js";

const allowed = ["pdf", "docx", "txt"];
const file = (name, size = 20, lastModified = 1) => ({ name, size, lastModified });
const add = (files, roles, incoming) => addSelectedFiles(files, roles, incoming, 1, allowed);

test("selecting one file assigns question paper", () => {
    const result = add([], [], [file("paper.pdf")]);
    assert.deepEqual(result.files.map((item) => item.name), ["paper.pdf"]);
    assert.deepEqual(result.roles, ["question_paper"]);
    assert.equal(result.error, "");
});

test("selecting two files together assigns question paper and answer key", () => {
    const result = add([], [], [file("paper.pdf"), file("key.pdf")]);
    assert.deepEqual(result.roles, ["question_paper", "answer_key"]);
    assert.equal(result.files.length, 2);
});

test("adding a second file appends it and preserves the first file role", () => {
    const first = file("paper.pdf");
    const result = add([first], ["question_paper"], [file("key.pdf")]);
    assert.deepEqual(result.files, [first, file("key.pdf")]);
    assert.deepEqual(result.roles, ["question_paper", "answer_key"]);
});

test("drag-and-drop file lists append through the same selection path", () => {
    const result = add([file("paper.pdf")], ["question_paper"], [file("key.pdf"), file("paper.pdf")]);
    assert.deepEqual(result.files.map((item) => item.name), ["paper.pdf", "key.pdf"]);
    assert.deepEqual(result.roles, ["question_paper", "answer_key"]);
});

test("roles can be changed while preserving exactly one question paper", () => {
    assert.deepEqual(changeFileRole(["question_paper", "answer_key"], 1, "question_paper"), ["answer_key", "question_paper"]);
    assert.equal(validateFileRoles(["answer_key", "question_paper"]), "");
});

test("removing one file leaves the other file's role untouched", () => {
    const result = removeSelectedFile([file("paper.pdf"), file("key.pdf")], ["question_paper", "answer_key"], 0);
    assert.deepEqual(result.files.map((item) => item.name), ["key.pdf"]);
    assert.deepEqual(result.roles, ["answer_key"]);
});

test("duplicate files are not appended", () => {
    const result = add([file("paper.pdf")], ["question_paper"], [file("paper.pdf")]);
    assert.equal(result.files.length, 1);
    assert.equal(result.error, "");
});

test("two question papers and two answer keys are rejected", () => {
    assert.equal(validateFileRoles(["question_paper", "question_paper"]), "Choose only one question paper.");
    assert.equal(validateFileRoles(["answer_key", "answer_key"]), "Choose exactly one question paper before processing.");
});

test("one question paper plus one answer key is submittable", () => {
    const selection = add([], [], [file("paper.pdf"), file("key.pdf")]);
    assert.equal(selection.error, "");
    assert.equal(validateFileRoles(selection.roles), "");
});

test("question paper and answer key use repeated multipart files plus one roles map", () => {
    const paper = new File(["paper"], "paper.pdf", { type: "application/pdf" });
    const key = new File(["key"], "key.pdf", { type: "application/pdf" });
    const form = createUploadFormData([paper, key], { "paper.pdf": "question_paper", "key.pdf": "answer_key" });
    assert.equal(form.getAll("files").length, 2);
    assert.deepEqual(form.getAll("files").map((item) => item.name), ["paper.pdf", "key.pdf"]);
    assert.deepEqual(JSON.parse(form.get("roles")), { "paper.pdf": "question_paper", "key.pdf": "answer_key" });
});

test("combined size, empty and unsupported files are rejected", () => {
    assert.match(add([file("paper.pdf", 700000)], ["question_paper"], [file("key.txt", 400000)]).error, /Combined upload/);
    assert.match(add([], [], [file("empty.txt", 0)]).error, /empty/);
    assert.match(add([], [], [file("unknown.csv")]).error, /unsupported/);
});

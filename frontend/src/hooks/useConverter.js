import { useCallback, useEffect, useRef, useState } from "react";
import {
    ACCEPTED_EXTENSIONS, MAX_UPLOAD_MB, checkHealth, deleteConversion,
    downloadFile, getConversion, jsonUrl, uploadDocument, zipUrl,
} from "../services/converterApi";
import { addSelectedFiles, changeFileRole, removeSelectedFile, validateFileRoles } from "../utils/fileSelection";

const POLL_INTERVAL_MS = 1200;
const IN_PROGRESS = ["queued", "processing"];

function wait(milliseconds, signal) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(resolve, milliseconds);
        signal.addEventListener("abort", () => {
            clearTimeout(timer);
            reject(new DOMException("Cancelled", "AbortError"));
        }, { once: true });
    });
}

export function useConverter() {
    const [files, setFiles] = useState([]);
    const [roles, setRoles] = useState([]);
    const [phase, setPhase] = useState("idle");
    const [uploadProgress, setUploadProgress] = useState(0);
    const [progress, setProgress] = useState(0);
    const [stage, setStage] = useState("");
    const [result, setResult] = useState(null);
    const [conversionId, setConversionId] = useState(null);
    const [error, setError] = useState("");
    const [downloading, setDownloading] = useState(null);
    const [downloadError, setDownloadError] = useState("");
    const controllerRef = useRef(null);
    const busyRef = useRef(false);
    const conversionIdRef = useRef(null);
    const file = files[0] ?? null;
    const questionPaperFile = files[roles.indexOf("question_paper")] ?? file;

    const clearState = useCallback(() => {
        setFiles([]); setRoles([]); setPhase("idle"); setUploadProgress(0);
        setProgress(0); setStage(""); setResult(null); setConversionId(null);
        setError(""); setDownloadError("");
    }, []);

    const reset = useCallback(() => {
        controllerRef.current?.abort();
        controllerRef.current = null;
        busyRef.current = false;
        const previousId = conversionIdRef.current;
        conversionIdRef.current = null;
        if (previousId) deleteConversion(previousId).catch(() => {});
        clearState();
    }, [clearState]);

    const selectFiles = useCallback((incoming) => {
        if (busyRef.current) return;
        if (!Array.from(incoming ?? []).length) return;
        const selected = addSelectedFiles(files, roles, incoming, MAX_UPLOAD_MB, ACCEPTED_EXTENSIONS);
        setError(selected.error);
        if (selected.error) return;
        if (phase === "completed" || phase === "failed") {
            const previousId = conversionIdRef.current;
            conversionIdRef.current = null;
            if (previousId) deleteConversion(previousId).catch(() => {});
            setPhase("idle"); setResult(null); setConversionId(null); setProgress(0); setStage(""); setUploadProgress(0);
        }
        setFiles(selected.files);
        setRoles(selected.roles);
    }, [files, roles, phase]);

    const setFileRole = useCallback((index, role) => {
        setRoles((current) => changeFileRole(current, index, role));
        setError("");
    }, []);

    const removeFile = useCallback((index) => {
        const removed = removeSelectedFile(files, roles, index);
        setFiles(removed.files);
        setRoles(removed.roles);
        if (phase === "completed" || phase === "failed") {
            const previousId = conversionIdRef.current;
            conversionIdRef.current = null;
            if (previousId) deleteConversion(previousId).catch(() => {});
            setPhase("idle"); setResult(null); setConversionId(null); setProgress(0); setStage(""); setUploadProgress(0);
        }
        setError("");
    }, [files, roles, phase]);

    const runConversion = useCallback(async () => {
        if (busyRef.current) return;
        const roleError = validateFileRoles(roles);
        if (!files.length) { setError("Select at least one file before processing."); return; }
        if (roleError) { setError(roleError); return; }
        const controller = new AbortController();
        controllerRef.current = controller;
        busyRef.current = true;
        setError(""); setPhase("uploading"); setUploadProgress(0);
        try {
            await checkHealth(controller.signal);
            const roleMap = Object.fromEntries(files.map((item, index) => [item.name, roles[index]]));
            const created = await uploadDocument(files, { roles: roleMap, signal: controller.signal, onProgress: setUploadProgress });
            conversionIdRef.current = created.conversion_id;
            setConversionId(created.conversion_id);
            setUploadProgress(100); setPhase("processing");
            let status = created;
            while (IN_PROGRESS.includes(status.status)) {
                setProgress(status.progress ?? 0); setStage(status.stage ?? "");
                await wait(POLL_INTERVAL_MS, controller.signal);
                status = await getConversion(created.conversion_id, controller.signal);
            }
            if (status.status !== "completed" || !status.result) throw new Error(status.error || "The conversion failed.");
            setResult({
                ...status.result,
                document: {
                    ...status.result.document,
                    source_filename: files[roles.indexOf("question_paper")].name,
                },
            });
            setProgress(100); setPhase("completed");
        } catch (caught) {
            if (controller.signal.aborted) return;
            setError(caught.message); setPhase("failed");
        } finally {
            if (controllerRef.current === controller) busyRef.current = false;
        }
    }, [files, roles]);

    const download = useCallback(async (kind) => {
        if (!conversionId || downloading) return;
        const stem = questionPaperFile?.name.replace(/\.[^.]+$/, "") || "docujson";
        setDownloading(kind); setDownloadError("");
        try {
            await downloadFile(kind === "zip" ? zipUrl(conversionId) : jsonUrl(conversionId), kind === "zip" ? `${stem}_with_media.zip` : `${stem}.json`);
        } catch (caught) { setDownloadError(caught.message); }
        finally { setDownloading(null); }
    }, [conversionId, downloading, questionPaperFile]);

    useEffect(() => () => controllerRef.current?.abort(), []);
    return { file, files, roles, phase, uploadProgress, progress, stage, result, conversionId, error, downloading, downloadError, selectFiles, setFileRole, removeFile, runConversion, reset, download };
}

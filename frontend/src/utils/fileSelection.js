export function addSelectedFiles(existingFiles, existingRoles, incomingFiles, maxUploadMb, acceptedExtensions) {
    const files = [...existingFiles];
    const roles = [...existingRoles];
    const known = new Set(files.map((file) => `${file.name}\0${file.size}\0${file.lastModified}`));
    const knownNames = new Set(files.map((file) => file.name));

    for (const file of Array.from(incomingFiles ?? [])) {
        const fingerprint = `${file.name}\0${file.size}\0${file.lastModified}`;
        if (known.has(fingerprint)) continue;
        if (knownNames.has(file.name)) return { files: existingFiles, roles: existingRoles, error: `A different selected file is already named ${file.name}. Rename one file so its role can be identified.` };
        if (files.length >= 2) return { files: existingFiles, roles: existingRoles, error: "Upload one question paper and optionally one answer key (maximum two files)." };
        const extension = file.name.split(".").pop()?.toLowerCase();
        if (!acceptedExtensions.includes(extension)) return { files: existingFiles, roles: existingRoles, error: `${file.name}: unsupported file type. Select PDF, DOCX, or TXT files.` };
        if (file.size === 0) return { files: existingFiles, roles: existingRoles, error: `${file.name}: file is empty.` };
        if (files.reduce((total, selected) => total + selected.size, file.size) > maxUploadMb * 1024 * 1024) {
            return { files: existingFiles, roles: existingRoles, error: `Combined upload exceeds the ${maxUploadMb} MB limit.` };
        }
        files.push(file);
        const questionPaperAlreadySelected = roles.includes("question_paper");
        roles.push(questionPaperAlreadySelected ? "answer_key" : "question_paper");
        known.add(fingerprint);
        knownNames.add(file.name);
    }

    return { files, roles, error: "" };
}

export function changeFileRole(roles, index, role) {
    return roles.map((currentRole, currentIndex) => {
        if (currentIndex === index) return role;
        return role === "question_paper" ? "answer_key" : currentRole;
    });
}

export function removeSelectedFile(files, roles, index) {
    return {
        files: files.filter((_, currentIndex) => currentIndex !== index),
        roles: roles.filter((_, currentIndex) => currentIndex !== index),
    };
}

export function validateFileRoles(roles) {
    const questionPaperCount = roles.filter((role) => role === "question_paper").length;
    if (questionPaperCount === 0) return "Choose exactly one question paper before processing.";
    if (questionPaperCount > 1) return "Choose only one question paper.";
    if (roles.some((role) => role !== "question_paper" && role !== "answer_key")) return "Choose a valid role for every file.";
    return "";
}

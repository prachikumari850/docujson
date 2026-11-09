export function createUploadFormData(files, roles) {
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file, file.name));
    form.append("roles", JSON.stringify(roles));
    return form;
}

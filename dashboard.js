function refreshAll() {
    document.querySelectorAll("iframe").forEach((frame) => {
        frame.src = frame.src;
    });
}


document.addEventListener("keydown", (event) => {
    if (event.key.toLowerCase() === "r") {
        refreshAll();
    }
});
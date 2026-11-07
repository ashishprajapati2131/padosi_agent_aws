
function copyAppsScriptCode() {
    var code = document.getElementById("appsScriptCodeText").innerText;
    navigator.clipboard.writeText(code).then(function() {
        var btn = document.getElementById("btnCopyScript");
        var oldText = btn.innerHTML;
        btn.innerHTML = "✅ Copied!";
        btn.classList.remove("btn-primary");
        btn.classList.add("btn-success");
        setTimeout(function() {
            btn.innerHTML = oldText;
            btn.classList.remove("btn-success");
            btn.classList.add("btn-primary");
        }, 2000);
    }).catch(function(err) {
        alert("Please select and copy the code manually.");
    });
}

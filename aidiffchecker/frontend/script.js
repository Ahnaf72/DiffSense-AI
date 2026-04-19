const loginForm = document.getElementById("loginForm");

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const formData = new FormData(loginForm);
  const response = await fetch("http://127.0.0.1:8000/login", {
    method: "POST",
    body: formData
  });

  const result = await response.json();

  alert(result.message); // Shows "Logged in!" or "Invalid credentials"
});

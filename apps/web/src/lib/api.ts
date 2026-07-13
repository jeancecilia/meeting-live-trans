const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

let isRefreshing = false;
let failedQueue: Array<{ resolve: (value: Response) => void; reject: (reason?: any) => void; }> = [];

const processQueue = (error: Error | null, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      // The calling interceptor will retry the request with the new token
      prom.resolve(new Response(null, { status: 200 })); // dummy signal
    }
  });
  failedQueue = [];
};

export async function apiFetch(
  path: string,
  options?: RequestInit,
): Promise<Response> {
  const token = typeof window !== "undefined"
    ? localStorage.getItem("access_token")
    : null;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  // Intercept 401s and try to refresh token
  if (response.status === 401 && typeof window !== "undefined" && !path.includes("/api/auth/")) {
    const refreshToken = localStorage.getItem("refresh_token");
    if (refreshToken) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then(() => {
          const newToken = localStorage.getItem("access_token");
          headers["Authorization"] = `Bearer ${newToken}`;
          return fetch(`${API_URL}${path}`, { ...options, headers });
        }).catch(err => {
          return response;
        });
      }

      isRefreshing = true;

      try {
        const refreshResponse = await fetch(`${API_URL}/api/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });

        if (refreshResponse.ok) {
          const data = await refreshResponse.json();
          localStorage.setItem("access_token", data.access_token);
          localStorage.setItem("refresh_token", data.refresh_token);
          
          headers["Authorization"] = `Bearer ${data.access_token}`;
          
          processQueue(null, data.access_token);
          
          // Retry original request
          return fetch(`${API_URL}${path}`, {
            ...options,
            headers,
          });
        } else {
          // Refresh token is invalid/expired
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          processQueue(new Error("Refresh failed"));
          window.location.href = "/login";
        }
      } catch (err) {
        processQueue(err as Error);
      } finally {
        isRefreshing = false;
      }
    } else {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
    }
  }

  return response;
}

export function getApiUrl(): string {
  return API_URL;
}

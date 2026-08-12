export async function authFetch<T>(
  path: string,
  token: string,
  opts: RequestInit = {}
): Promise<T | null> {
  const res = await fetch(path, {
    ...opts,
    headers: { ...opts.headers, Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  return res.json();
}

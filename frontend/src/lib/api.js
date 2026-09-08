// Same-origin requests work behind both the Vite and production nginx proxies.
export async function requestJson(url, options = {}) {
  const response = await fetch(url, options)
  let data
  try {
    data = await response.json()
  } catch {
    throw new Error('The server returned an invalid response. Check that the backend is available.')
  }
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg).join('; ')
      : data.detail
    const error = new Error(data.message || detail || 'The request failed. Please try again.')
    error.status = response.status
    throw error
  }
  return data
}

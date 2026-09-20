/** Both download controls resolve freshness on the server before opening S3. */
export async function requestTracedDownload(movieId, apiKey, analysisLeaseId) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
        const response = await fetch(`${LAMBDA_API_BASE}resize-api/v1/download-traced`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'x-api-key': apiKey},
            body: JSON.stringify({movie_id: movieId, analysis_lease_id: analysisLeaseId || null}),
            signal: controller.signal,
        });
        const data = await response.json();
        if (!response.ok || data.error) throw new Error(data.message || 'Unable to prepare the traced movie download.');
        return data;
    } finally {
        clearTimeout(timeout);
    }
}

export function openTracedDownload(url) {
    const link = document.createElement('a');
    link.href = url;
    link.download = '';
    document.body.appendChild(link);
    link.click();
    link.remove();
}

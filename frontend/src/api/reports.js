import http, { toParams } from './client.js'

export const listReports = (params) => http.get('/reports', { params: toParams(params) })
export const getReport = (id) => http.get(`/reports/${id}`)
export const previewReport = (params) => http.get('/reports/preview', { params: toParams(params) })
export const generateReport = (payload) => http.post('/reports', payload)
export const deleteReport = (id) => http.delete(`/reports/${id}`)
export const exportReportUrl = (id) => `/reports/${id}/export`

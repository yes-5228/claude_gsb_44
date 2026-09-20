import http, { toParams } from './client.js'

export const listReports = (params) => http.get('/reports', { params: toParams(params) })
export const generateReport = (payload) => http.post('/reports', payload)
export const getReport = (reportId) => http.get(`/reports/${reportId}`)
export const removeReport = (reportId) => http.delete(`/reports/${reportId}`)
export const reportOptions = () => http.get('/reports/options')
export const exportReportUrl = (reportId) => `/reports/${reportId}/export`

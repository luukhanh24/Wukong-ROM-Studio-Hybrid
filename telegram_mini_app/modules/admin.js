import { state } from './state.js';
let panel;
let loading;
export function loadAdminPanel() {
  if (!loading) loading = import('./admin-panel.js').then(value => panel = value).catch(error => { loading = undefined; throw error; });
  return loading;
}
export function renderAdminReleaseEditor(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.renderAdminReleaseEditor(...args);
  return loadAdminPanel().then(module => module.renderAdminReleaseEditor(...args));
}
export function savePermanentReleaseVersion(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.savePermanentReleaseVersion(...args);
  return loadAdminPanel().then(module => module.savePermanentReleaseVersion(...args));
}
export function batchSelections(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.batchSelections(...args);
  return loadAdminPanel().then(module => module.batchSelections(...args));
}
export function setBatchSelections(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.setBatchSelections(...args);
  return loadAdminPanel().then(module => module.setBatchSelections(...args));
}
export function updateBatchSummary(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.updateBatchSummary(...args);
  return loadAdminPanel().then(module => module.updateBatchSummary(...args));
}
export function renderBatchChoices(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.renderBatchChoices(...args);
  return loadAdminPanel().then(module => module.renderBatchChoices(...args));
}
export function openBatchBuildPage(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.openBatchBuildPage(...args);
  return loadAdminPanel().then(module => module.openBatchBuildPage(...args));
}
export function closeBatchBuildPage(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.closeBatchBuildPage(...args);
  return loadAdminPanel().then(module => module.closeBatchBuildPage(...args));
}
export function batchReleaseSummary(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.batchReleaseSummary(...args);
  return loadAdminPanel().then(module => module.batchReleaseSummary(...args));
}
export function renderBatch(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.renderBatch(...args);
  return loadAdminPanel().then(module => module.renderBatch(...args));
}
export function loadBatch(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.loadBatch(...args);
  return loadAdminPanel().then(module => module.loadBatch(...args));
}
export function loadLatestBatch(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.loadLatestBatch(...args);
  return loadAdminPanel().then(module => module.loadLatestBatch(...args));
}
export function startBatchBuild(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.startBatchBuild(...args);
  return loadAdminPanel().then(module => module.startBatchBuild(...args));
}
export function renderMaintenanceAdmin(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.renderMaintenanceAdmin(...args);
  return loadAdminPanel().then(module => module.renderMaintenanceAdmin(...args));
}
export function updateMaintenance(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.updateMaintenance(...args);
  return loadAdminPanel().then(module => module.updateMaintenance(...args));
}
export function renderAdminUsers(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.renderAdminUsers(...args);
  return loadAdminPanel().then(module => module.renderAdminUsers(...args));
}
export function loadAdminUsers(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.loadAdminUsers(...args);
  return loadAdminPanel().then(module => module.loadAdminUsers(...args));
}
export function adminAuditArticle(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.adminAuditArticle(...args);
  return loadAdminPanel().then(module => module.adminAuditArticle(...args));
}
export function scheduleAdminUserActivityPoll(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.scheduleAdminUserActivityPoll(...args);
  return loadAdminPanel().then(module => module.scheduleAdminUserActivityPoll(...args));
}
export function refreshAdminUserActivity(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.refreshAdminUserActivity(...args);
  return loadAdminPanel().then(module => module.refreshAdminUserActivity(...args));
}
export function requestAdminAction(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.requestAdminAction(...args);
  return loadAdminPanel().then(module => module.requestAdminAction(...args));
}
export function runAdminUserAction(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.runAdminUserAction(...args);
  return loadAdminPanel().then(module => module.runAdminUserAction(...args));
}
export function openAdminUser(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.openAdminUser(...args);
  return loadAdminPanel().then(module => module.openAdminUser(...args));
}
export function renderAdminPresetLabels(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.renderAdminPresetLabels(...args);
  return loadAdminPanel().then(module => module.renderAdminPresetLabels(...args));
}
export function savePermanentPresetLabels(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.savePermanentPresetLabels(...args);
  return loadAdminPanel().then(module => module.savePermanentPresetLabels(...args));
}
export function openCacheClearDialog(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.openCacheClearDialog(...args);
  return loadAdminPanel().then(module => module.openCacheClearDialog(...args));
}
export function performCacheClear(...args) {
  if (state.me?.role !== 'admin') return Promise.resolve();
  if (panel) return panel.performCacheClear(...args);
  return loadAdminPanel().then(module => module.performCacheClear(...args));
}

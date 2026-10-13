{{/* SPDX-License-Identifier: AGPL-3.0-or-later */}}

{{- define "kaleta.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "kaleta.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "kaleta.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "kaleta.labels" -}}
app.kubernetes.io/name: {{ include "kaleta.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "kaleta.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kaleta.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "kaleta.postgres.fullname" -}}
{{- printf "%s-postgres" (include "kaleta.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "kaleta.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- include "kaleta.fullname" . -}}
{{- end -}}
{{- end -}}

{{/*
The public URL: explicit app.publicUrl, else https://<ingress.host> when the
ingress is on, else empty (the app falls back to its own default).
*/}}
{{- define "kaleta.publicUrl" -}}
{{- if .Values.app.publicUrl -}}
{{- .Values.app.publicUrl -}}
{{- else if .Values.ingress.enabled -}}
{{- printf "https://%s" .Values.ingress.host -}}
{{- end -}}
{{- end -}}

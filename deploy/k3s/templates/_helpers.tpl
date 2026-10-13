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

{{/*
The SQLAlchemy async DB URL. Bundled Postgres: built from the app role and the
in-cluster service name. External: the URL given verbatim. Fails loudly when
postgres is disabled and no external URL is set, so a misconfigured release
never renders a Secret with an empty URL.
*/}}
{{- define "kaleta.dbUrl" -}}
{{- if .Values.postgres.enabled -}}
{{- $pg := .Values.postgres -}}
{{- printf "postgresql+asyncpg://%s:%s@%s:5432/%s" $pg.appUser $pg.appPassword (include "kaleta.postgres.fullname" .) $pg.database -}}
{{- else if .Values.externalDatabase.url -}}
{{- .Values.externalDatabase.url -}}
{{- else -}}
{{- fail "postgres.enabled is false but externalDatabase.url is empty — set one." -}}
{{- end -}}
{{- end -}}

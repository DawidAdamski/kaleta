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

{{- define "kaleta.valkey.fullname" -}}
{{- printf "%s-valkey" (include "kaleta.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
The Valkey (KALETA_REDIS_URL) the app uses, or empty when none is configured:
the bundled instance's in-cluster service when redis.enabled, else redis.url.
*/}}
{{- define "kaleta.redisUrl" -}}
{{- if .Values.redis.enabled -}}
{{- printf "redis://%s:6379/0" (include "kaleta.valkey.fullname" .) -}}
{{- else -}}
{{- .Values.redis.url -}}
{{- end -}}
{{- end -}}

{{/*
Guard the multi-replica path: more than one replica needs Valkey (shared
sessions + rate-limit) and sticky sessions (the in-process KeyRing needs client
affinity). Fails rendering with a sentence rather than shipping a broken deploy.
*/}}
{{- define "kaleta.validateScaling" -}}
{{- if and .Values.redis.enabled .Values.redis.url -}}
{{- fail "redis.enabled and redis.url are both set — pick one. The bundled Valkey would otherwise silently win over your external url." -}}
{{- end -}}
{{- if and .Values.ingress.stickySessions (ne .Values.ingress.className "traefik") -}}
{{- fail "ingress.stickySessions renders Traefik annotations and is a no-op on other ingress controllers. Set ingress.className=traefik, or configure client affinity on your own ingress and adapt the chart." -}}
{{- end -}}
{{- if gt (int .Values.replicaCount) 1 -}}
{{- if not (include "kaleta.redisUrl" .) -}}
{{- fail "replicaCount > 1 requires Valkey: set redis.enabled=true or redis.url. Keys are never stored there — only sessions and rate-limit counters." -}}
{{- end -}}
{{- if not .Values.ingress.stickySessions -}}
{{- fail "replicaCount > 1 requires ingress.stickySessions=true: without client affinity a request can land on a pod whose KeyRing never took the unlock." -}}
{{- end -}}
{{- end -}}
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

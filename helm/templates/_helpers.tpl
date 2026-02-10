{{/*
Fullname for the FastAPI app (release-prefixed, truncated to 63 chars).
*/}}
{{- define "fastapi-k8s.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels for the FastAPI app.
*/}}
{{- define "fastapi-k8s.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels for the FastAPI app.
*/}}
{{- define "fastapi-k8s.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Fullname for Redis resources.
*/}}
{{- define "fastapi-k8s.redisFullname" -}}
{{- printf "%s-redis" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels for Redis.
*/}}
{{- define "fastapi-k8s.redisLabels" -}}
app.kubernetes.io/name: redis
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels for Redis.
*/}}
{{- define "fastapi-k8s.redisSelectorLabels" -}}
app.kubernetes.io/name: redis
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "promptcloak.name" -}}
promptcloak
{{- end -}}

{{- define "promptcloak.fullname" -}}
{{- if contains (include "promptcloak.name" .) .Release.Name -}}
{{ .Release.Name }}
{{- else -}}
{{ .Release.Name }}-{{ include "promptcloak.name" . }}
{{- end -}}
{{- end -}}

{{- define "promptcloak.serverApiKey" -}}
{{- if .Values.serverAuth.apiKey -}}
{{- .Values.serverAuth.apiKey -}}
{{- else if hasKey .Values.secretEnv "PROMPTCLOAK_SERVER_API_KEY" -}}
{{- index .Values.secretEnv "PROMPTCLOAK_SERVER_API_KEY" -}}
{{- else -}}
{{- $secretName := printf "%s-secret" (include "promptcloak.fullname" .) -}}
{{- $existing := lookup "v1" "Secret" .Release.Namespace $secretName -}}
{{- if and $existing (hasKey $existing.data "PROMPTCLOAK_SERVER_API_KEY") -}}
{{- index $existing.data "PROMPTCLOAK_SERVER_API_KEY" | b64dec -}}
{{- else -}}
{{- randAlphaNum 48 -}}
{{- end -}}
{{- end -}}
{{- end -}}

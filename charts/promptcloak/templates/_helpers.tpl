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

{{- define "promptcloak.name" -}}
promptcloak
{{- end -}}

{{- define "promptcloak.fullname" -}}
{{ .Release.Name }}-{{ include "promptcloak.name" . }}
{{- end -}}

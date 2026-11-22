"""Duração fixa de uma sessão de atendimento.

Porta shared/scheduling/session-duration.ts. O modelo Appointment não
guarda uma duração por sessão — estas constantes são a simplificação
assumida.

- SESSION_DURATION_MINUTES: a consulta em si (hora clínica, 50 min) — é o
  que o PACIENTE precisa ter livre.
- ROOM_TURNOVER_MINUTES: intervalo depois da consulta para o estagiário
  organizar a sala.
- SLOT_MINUTES: o bloco que a consulta ocupa do ESTAGIÁRIO e da SALA
  (consulta + intervalo = 1 h). É o que vale no pareamento (a janela do
  estagiário precisa comportar o bloco) e no conflito de sala.
"""

SESSION_DURATION_MINUTES = 50
ROOM_TURNOVER_MINUTES = 10
SLOT_MINUTES = SESSION_DURATION_MINUTES + ROOM_TURNOVER_MINUTES

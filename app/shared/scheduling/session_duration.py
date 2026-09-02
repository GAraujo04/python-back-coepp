"""Duração fixa de uma sessão de atendimento (hora clínica padrão).

Porta shared/scheduling/session-duration.ts. Usada tanto na checagem de
sobreposição de disponibilidade quanto na checagem de conflito de sala. O
modelo Appointment não guarda uma duração por sessão — esta constante é a
simplificação assumida (mesma do original).
"""

SESSION_DURATION_MINUTES = 50

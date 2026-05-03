from pydantic import BaseModel, Field

class TransactionInputSchema(BaseModel):
    """Esquema de validação para o payload de entrada de inferência.
    Campos conforme BaseDefault01.csv."""
    renda:        float = Field(..., description="Renda mensal do cliente (R$)",          ge=0.0,  example=4500.0)
    idade:        float = Field(..., description="Idade do cliente (anos)",                ge=0.0,  example=42.0)
    etnia:        int   = Field(..., description="Etnia (codificada numericamente)",       ge=0,    example=0)
    sexo:         int   = Field(..., description="Sexo (0=feminino, 1=masculino)",         ge=0,    example=1)
    casapropria:  int   = Field(..., description="Possui casa própria (0=não, 1=sim)",     ge=0,    example=1)
    outrasrendas: int   = Field(..., description="Possui outras fontes de renda (0/1)",   ge=0,    example=0)
    estadocivil:  int   = Field(..., description="Estado civil (codificado numericamente)",ge=0,    example=1)
    escolaridade: int   = Field(..., description="Nível de escolaridade (0–3)",            ge=0,    example=2)

class ScoreOutputSchema(BaseModel):
    """Esquema de validação para o payload de saída."""
    score_predito:       int   = Field(..., description="1 para Alto Risco/Default, 0 para Baixo Risco")
    score_probabilidade: float = Field(..., description="Probabilidade de inadimplência (0.0–1.0)")
    score_level:         str   = Field(..., description="Nível de risco: Baixo (<30%), Médio (30–60%), Alto (>60%)")
    risco_interpretavel: str   = Field(..., description="Classificação semântica de negócio")

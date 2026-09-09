abstract Metonymy = {
  flags startcat = S ;

  cat
    S ;
    NP ;
    VP ;
    V2 ;
    PP ;
    CN ;

  fun
    Pred : NP -> VP -> S ;
    NegPred : NP -> VP -> S ;
    Compl : V2 -> NP -> VP ;
    PassCompl : V2 -> NP -> VP ;
    InPP : NP -> PP ;
    AboutPP : NP -> PP ;
    WithPP : NP -> PP ;
    ForPP : NP -> PP ;
    OnPP : NP -> PP ;
    AtPP : NP -> PP ;
    FromPP : NP -> PP ;
    ByPP : NP -> PP ;
    OverPP : NP -> PP ;
    UnderPP : NP -> PP ;
    DuringPP : NP -> PP ;
    NearPP : NP -> PP ;
    AndS : S -> S -> S ;
    OrS : S -> S -> S ;
    AndNP : NP -> NP -> NP ;
    OrNP : NP -> NP -> NP ;
    PredConjVP : NP -> VP -> VP -> S ;
    PredOrConjVP : NP -> VP -> VP -> S ;
    PredCopNP : NP -> NP -> S ;
    ModifyNP : NP -> PP -> NP ;
    ModifyRel : NP -> V2 -> NP -> NP ;
    ModifyRelVP : NP -> VP -> NP ;
    IndefCN : CN -> NP ;
    DefCN : CN -> NP ;
    ModifyRelCN : CN -> V2 -> NP -> CN ;
    ModifyRelCNVP : CN -> VP -> CN ;
    PossNP : NP -> CN -> NP ;
    EveryCN : String -> String -> NP ;
    OpenAdjDefCN : String -> String -> String -> NP ;
    OpenAdjIndefCN : String -> String -> String -> NP ;
    Announce : V2 ;
    OpenPN : String -> NP ;
    OpenPN2 : String -> String -> NP ;
    OpenPN3 : String -> String -> String -> NP ;
    OpenIndefCN : String -> String -> NP ;
    OpenDefCN : String -> String -> NP ;
    OpenAgentive : V2 ;
    OpenEventive : V2 ;
    OpenArtifactive : V2 ;
    OpenConsumptive : V2 ;
    OpenProductUse : V2 ;
    OpenSourceNP : NP ;
    OpenTargetNP : NP ;
    OpenContextNP : NP ;

    -- Fronted/trailing subordinate clauses ("Because X, Y"/"Y, because
    -- X") -- see grammar/MetonymyEng.gf for why these need SentenceEng's
    -- ExtAdvS/SSubjS specifically (not the plain mkS : Adv -> S -> S
    -- overload, which omits the comma). because_Subj/if_Subj/when_Subj/
    -- although_Subj are closed RGL vocabulary, matching the same
    -- closed-word-per-function idiom already used for the 8 prepositions
    -- above -- no open-ended String parameter, so no PrepPP-class
    -- ambiguity risk.
    BecauseS : S -> S -> S ;
    IfS : S -> S -> S ;
    WhenS : S -> S -> S ;
    AlthoughS : S -> S -> S ;
    SBecauseS : S -> S -> S ;
    SIfS : S -> S -> S ;
    SWhenS : S -> S -> S ;
    SAlthoughS : S -> S -> S ;

    -- Short (1-2 word) comma-delimited appositive ("Waterloo, Ontario,
    -- announces..."), via the same hand-rolled String-concatenation
    -- idiom OpenPN/OpenPN2/OpenPN3 already use -- a literal comma
    -- spliced into the NP's own string, so it plugs directly into the
    -- existing Pred/Compl/PredCopNP with no new S-level machinery.
    -- Deliberately bounded (not a general free-text capture): GF's
    -- String parameter matches exactly one token during parsing, so an
    -- arbitrary-length appositive is not achievable this way -- see
    -- docs/contextual-tower.md for the full reasoning and what was
    -- deliberately deferred.
    ApposCommaPN1 : String -> String -> NP ;
    ApposCommaPN2 : String -> String -> String -> NP ;

    Anna : NP ;
    Alice : NP ;
    Bob : NP ;
    John : NP ;
    Mary : NP ;
    Tolstoy : NP ;
    WarAndPeace : NP ;
    AnnaKarenina : NP ;
    WorksOfTolstoy : NP ;
    Glass : NP ;
    ContentsOfGlass : NP ;
    Moscow : NP ;
    RussianGovernment : NP ;
    Agreement : NP ;

    Read : V2 ;
    Drink : V2 ;
    Sign : V2 ;
}

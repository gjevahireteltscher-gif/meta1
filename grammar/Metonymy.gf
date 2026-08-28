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
    InPP : NP -> PP ;
    AboutPP : NP -> PP ;
    WithPP : NP -> PP ;
    ForPP : NP -> PP ;
    ModifyNP : NP -> PP -> NP ;
    ModifyRel : NP -> V2 -> NP -> NP ;
    IndefCN : CN -> NP ;
    DefCN : CN -> NP ;
    ModifyRelCN : CN -> V2 -> NP -> CN ;
    EveryCN : String -> String -> NP ;
    OpenAdjDefCN : String -> String -> String -> NP ;
    OpenAdjIndefCN : String -> String -> String -> NP ;
    Announce : V2 ;
    OpenPN : String -> NP ;
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

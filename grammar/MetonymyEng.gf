concrete MetonymyEng of Metonymy =
  open SyntaxEng, ParadigmsEng, (R=ResEng) in {

  lincat
    S = S ;
    NP = NP ;
    VP = VP ;
    V2 = V2 ;
    PP = Adv ;
    CN = CN ;

  lin
    Pred np vp = mkS (mkCl np vp) ;
    NegPred np vp = mkS negativePol (mkCl np vp) ;
    Compl verb object = mkVP verb object ;
    InPP np = SyntaxEng.mkAdv in_Prep np ;
    AboutPP np = SyntaxEng.mkAdv (mkPrep "about") np ;
    WithPP np = SyntaxEng.mkAdv (mkPrep "with") np ;
    ForPP np = SyntaxEng.mkAdv (mkPrep "for") np ;
    ModifyNP np pp = mkNP np pp ;
    ModifyRel np verb object =
      mkNP np (mkRS (mkRCl which_RP (mkVP verb object))) ;
    IndefCN noun = mkNP a_Det noun ;
    DefCN noun = mkNP the_Det noun ;
    ModifyRelCN noun verb object =
      mkCN noun (mkRS (mkRCl which_RP (mkVP verb object))) ;
    EveryCN singular plural =
      lin NP {
        s = \\_ => "every" ++ singular.s ;
        a = R.agrP3 R.Sg
        } ;
    OpenAdjDefCN adjective singular plural =
      lin NP {
        s = \\_ => "the" ++ adjective.s ++ singular.s ;
        a = R.agrP3 R.Sg
        } ;
    OpenAdjIndefCN adjective singular plural =
      lin NP {
        s = \\_ => "a" ++ adjective.s ++ singular.s ;
        a = R.agrP3 R.Sg
        } ;
    Announce = mkV2 "announce" ;
    OpenPN name =
      lin NP {s = \\_ => name.s ; a = R.agrP3 R.Sg} ;
    OpenIndefCN singular plural =
      lin NP {
        s = \\_ => "a" ++ singular.s ;
        a = R.agrP3 R.Sg
        } ;
    OpenDefCN singular plural =
      lin NP {
        s = \\_ => "the" ++ singular.s ;
        a = R.agrP3 R.Sg
        } ;
    OpenAgentive = mkV2 "represent" ;
    OpenEventive = mkV2 "host" ;
    OpenArtifactive = mkV2 "denote" ;
    OpenConsumptive = mkV2 "contain" ;
    OpenProductUse = mkV2 "produce" ;
    OpenSourceNP = mkNP (mkPN "source") ;
    OpenTargetNP = mkNP (mkPN "expanded target") ;
    OpenContextNP = mkNP (mkPN "context") ;

    Anna = mkNP (mkPN "Anna") ;
    Alice = mkNP (mkPN "Alice") ;
    Bob = mkNP (mkPN "Bob") ;
    John = mkNP (mkPN "John") ;
    Mary = mkNP (mkPN "Mary") ;
    Tolstoy = mkNP (mkPN "Tolstoy") ;
    WarAndPeace = mkNP (mkPN "War and Peace") ;
    AnnaKarenina = mkNP (mkPN "Anna Karenina") ;
    WorksOfTolstoy = mkNP (mkPN "Tolstoy's works") ;
    Glass = mkNP a_Det (mkCN (mkN "glass")) ;
    ContentsOfGlass =
      mkNP (mkPN "the contents of a glass") ;
    Moscow = mkNP (mkPN "Moscow") ;
    RussianGovernment =
      mkNP
        the_Det
        (mkCN (mkA "Russian") (mkN "government")) ;
    Agreement = mkNP the_Det (mkCN (mkN "agreement")) ;

    Read = mkV2 "read" ;
    Drink = mkV2 "drink" ;
    Sign = mkV2 "sign" ;
}

concrete MetonymyEng of Metonymy =
  open SyntaxEng, ExtendEng, VerbEng, ParadigmsEng, ExtraEng, (R=ResEng) in {

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
    -- ExtendEng qualifier required: ExtraEng (opened below for
    -- MkVPS/ConjVPS/PredVPS/BaseVPS) independently declares its own
    -- PassAgentVPSlash : VPSlash -> NP -> VP with the identical
    -- signature, which made this pre-existing unqualified call
    -- ambiguous the moment ExtraEng was added to `open` -- confirmed by
    -- reading Extra.gf's actual source, not guessed.
    PassCompl verb agent = ExtendEng.PassAgentVPSlash (SlashV2a verb) agent ;
    InPP np = SyntaxEng.mkAdv in_Prep np ;
    AboutPP np = SyntaxEng.mkAdv (mkPrep "about") np ;
    WithPP np = SyntaxEng.mkAdv (mkPrep "with") np ;
    ForPP np = SyntaxEng.mkAdv (mkPrep "for") np ;
    OnPP np = SyntaxEng.mkAdv (mkPrep "on") np ;
    AtPP np = SyntaxEng.mkAdv (mkPrep "at") np ;
    FromPP np = SyntaxEng.mkAdv (mkPrep "from") np ;
    ByPP np = SyntaxEng.mkAdv (mkPrep "by") np ;
    OverPP np = SyntaxEng.mkAdv (mkPrep "over") np ;
    UnderPP np = SyntaxEng.mkAdv (mkPrep "under") np ;
    DuringPP np = SyntaxEng.mkAdv (mkPrep "during") np ;
    NearPP np = SyntaxEng.mkAdv (mkPrep "near") np ;
    AndS s1 s2 = mkS and_Conj s1 s2 ;
    OrS s1 s2 = mkS or_Conj s1 s2 ;
    AndNP np1 np2 = mkNP and_Conj np1 np2 ;
    OrNP np1 np2 = mkNP or_Conj np1 np2 ;
    PredConjVP np vp1 vp2 =
      ExtraEng.PredVPS np
        (ExtraEng.ConjVPS and_Conj
          (ExtraEng.BaseVPS
            (ExtraEng.MkVPS (mkTemp presentTense simultaneousAnt) positivePol vp1)
            (ExtraEng.MkVPS (mkTemp presentTense simultaneousAnt) positivePol vp2))) ;
    PredOrConjVP np vp1 vp2 =
      ExtraEng.PredVPS np
        (ExtraEng.ConjVPS or_Conj
          (ExtraEng.BaseVPS
            (ExtraEng.MkVPS (mkTemp presentTense simultaneousAnt) positivePol vp1)
            (ExtraEng.MkVPS (mkTemp presentTense simultaneousAnt) positivePol vp2))) ;
    ModifyNP np pp = mkNP np pp ;
    -- SyntaxEng qualifier required for the same reason as
    -- ExtendEng.PassAgentVPSlash above: ExtraEng.gf independently
    -- redefines its own `which_RP` local oper (line 336 of the pinned
    -- commit's ExtraEng.gf), which made this pre-existing unqualified
    -- reference ambiguous between it and ConstructorsEng.which_RP (the
    -- one already reachable via `open SyntaxEng`, and the one this
    -- always meant) the moment ExtraEng joined `open` -- confirmed
    -- directly from the real CI compiler's own ambiguity warning
    -- ("conflict ExtraEng.which_RP, ConstructorsEng.which_RP"), not
    -- guessed a second time.
    ModifyRel np verb object =
      mkNP np (mkRS (mkRCl SyntaxEng.which_RP (mkVP verb object))) ;
    IndefCN noun = mkNP a_Det noun ;
    DefCN noun = mkNP the_Det noun ;
    ModifyRelCN noun verb object =
      mkCN noun (mkRS (mkRCl SyntaxEng.which_RP (mkVP verb object))) ;
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

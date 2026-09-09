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
    -- Copula predication ("Henry County is a county in ..."), missing
    -- entirely before this: Compl/PassCompl are the only VP-building
    -- rules, both requiring a V2, so a bare "NP is NP2" sentence had no
    -- derivation at all. mkCl : NP -> NP -> Cl ("she is the woman") is
    -- already reachable via the existing `open SyntaxEng`, no new
    -- collision surface.
    PredCopNP np1 np2 = mkS (mkCl np1 np2) ;
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
    -- Generalizes ModifyRel to an arbitrary VP instead of a hardcoded
    -- V2+object: mkRCl : RP -> VP -> RCl is itself the general overload
    -- (ModifyRel above already routes through it via `mkVP verb
    -- object`), so this only relaxes our own abstract signature -- no
    -- new RGL surface. Lets a relative clause use Compl, PassCompl, or
    -- any future VP-building rule uniformly ("which signed X", "which
    -- was signed", ...).
    ModifyRelVP np vp = mkNP np (mkRS (mkRCl SyntaxEng.which_RP vp)) ;
    IndefCN noun = mkNP a_Det noun ;
    DefCN noun = mkNP the_Det noun ;
    ModifyRelCN noun verb object =
      mkCN noun (mkRS (mkRCl SyntaxEng.which_RP (mkVP verb object))) ;
    ModifyRelCNVP noun vp = mkCN noun (mkRS (mkRCl SyntaxEng.which_RP vp)) ;
    -- Possessive/genitive ("Tolstoy's works" as a live construction, not
    -- only the hand-written WorksOfTolstoy example): Extra.gf's
    -- GenNP : NP -> Quant combined with the already-confirmed
    -- mkNP : Quant -> CN -> NP. ExtraEng is already open (Phase 1); its
    -- full set of `conflict` warnings was already read in that CI run
    -- and GenNP was not among them.
    PossNP np cn = mkNP (ExtraEng.GenNP np) cn ;
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
    -- Confirmed via a dedicated CI diagnostic (test_gf_parse_diagnostic_matrix.py),
    -- not guessed: OpenPN's single `String` slot matches exactly one
    -- token when parsing, so a two-word name ("Henry County") never
    -- completed a derivation at all -- "Henry" alone via OpenPN, then
    -- nothing in the grammar could account for "County" immediately
    -- following it in subject position ("The parser failed at token 2:
    -- \"County\""). Most real WiMCor/ConMeC source mentions (place,
    -- institution, and person names) are two or three words, so this
    -- was blocking GF-parsing for a large fraction of sentences
    -- regardless of any sentence-level construction added elsewhere --
    -- explaining three consecutive contextual-tower-evaluation.yml runs
    -- that each measured zero effect from otherwise-correct grammar
    -- additions. OpenPN2/OpenPN3 give GF's chart parser an additional,
    -- explicit derivation to try for a two- or three-token span; they do
    -- not replace OpenPN (still tried for the one-token case), just add
    -- alternatives, exactly like Compl/PassCompl already coexist for the
    -- one VP-building slot.
    OpenPN2 first second =
      lin NP {s = \\_ => first.s ++ second.s ; a = R.agrP3 R.Sg} ;
    OpenPN3 first second third =
      lin NP {s = \\_ => first.s ++ second.s ++ third.s ; a = R.agrP3 R.Sg} ;
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

    -- Confirmed via the real, decisive text-free diagnostic added to
    -- score_contextual_detection.py (exit7_gf_sentence_signals): a
    -- comma is present in 87%/67% of the remaining WiMCor/ConMeC
    -- gf-parse-empty rows, far more than the 24%/3% that are still a
    -- proper-noun-length issue (run-4-or-more, which OpenPN2/OpenPN3
    -- don't cover). because_Subj/if_Subj/when_Subj/although_Subj are
    -- already reachable via SyntaxEng (Structural.gf is part of the
    -- already-open Syntax interface), likewise SyntaxEng.mkAdv's own
    -- Subj->S->Adv overload.
    --
    -- First attempt used SentenceEng.ExtAdvS/SSubjS directly (RGL's own
    -- comma-inserting combinators, `a.s ++ frontComma ++ s.s` with
    -- `frontComma = SOFT_BIND ++ ","`) -- confirmed by a real CI run to
    -- NOT parse ("Because Napoleon announces a programme, Waterloo
    -- announces a programme" failed at token 7, "announces"; the
    -- trailing form failed similarly). SOFT_BIND fuses the comma onto
    -- the preceding word as one glued terminal for linearization, which
    -- does not match how this grammar's own String-based vocabulary
    -- (OpenIndefCN's "programme", etc.) is tokenized elsewhere, so the
    -- two derivations disagree at the token level. The very same CI run
    -- proved the fix: ApposCommaPN1/ApposCommaPN2 below, which splice in
    -- a *plain* literal "," (no BIND) via ordinary Str concatenation,
    -- parsed successfully. So these fronted/trailing clauses now use
    -- that identical, already-proven idiom instead of ExtAdvS/SSubjS --
    -- hand-rolling the S record directly (S = {s : Str} in RGL's
    -- CatEng.gf, exactly as simple as NP's own s field) rather than
    -- going through SentenceEng at all, which also means no new `open`
    -- is needed here any more.
    BecauseS embedded main =
      lin S {s = (SyntaxEng.mkAdv because_Subj embedded).s ++ "," ++ main.s} ;
    IfS embedded main =
      lin S {s = (SyntaxEng.mkAdv if_Subj embedded).s ++ "," ++ main.s} ;
    WhenS embedded main =
      lin S {s = (SyntaxEng.mkAdv when_Subj embedded).s ++ "," ++ main.s} ;
    AlthoughS embedded main =
      lin S {s = (SyntaxEng.mkAdv although_Subj embedded).s ++ "," ++ main.s} ;
    SBecauseS main embedded =
      lin S {s = main.s ++ "," ++ (SyntaxEng.mkAdv because_Subj embedded).s} ;
    SIfS main embedded =
      lin S {s = main.s ++ "," ++ (SyntaxEng.mkAdv if_Subj embedded).s} ;
    SWhenS main embedded =
      lin S {s = main.s ++ "," ++ (SyntaxEng.mkAdv when_Subj embedded).s} ;
    SAlthoughS main embedded =
      lin S {s = main.s ++ "," ++ (SyntaxEng.mkAdv although_Subj embedded).s} ;

    -- Short comma-delimited appositive ("Waterloo, Ontario, announces a
    -- programme"). Deliberately bounded to 1-2 appositive words, not a
    -- general free-text capture: GF's String parameter matches exactly
    -- one token during parsing (the same confirmed limit that motivated
    -- OpenPN2/OpenPN3), so an arbitrary-length appositive would need a
    -- fundamentally different mechanism (a comma-bracketed recursive
    -- "list of words" category) -- deliberately deferred, see
    -- docs/contextual-tower.md, since it carries the same class of
    -- ambiguity risk that made the PrepPP experiment fail, at a larger,
    -- locally-unverifiable scale.
    ApposCommaPN1 name appos =
      lin NP {s = \\_ => name.s ++ "," ++ appos.s ++ ","; a = R.agrP3 R.Sg} ;
    ApposCommaPN2 name appos1 appos2 =
      lin NP {s = \\_ => name.s ++ "," ++ appos1.s ++ appos2.s ++ ","; a = R.agrP3 R.Sg} ;

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

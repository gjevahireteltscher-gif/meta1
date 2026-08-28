module Metonymy.Data
  ( AuthorWorkRow (..)
  , SemanticEntityRow (..)
  , SemanticRelationRow (..)
  , SubsortRow (..)
  , loadAuthorWorkRows
  , loadPredicates
  , loadActionRoleRequirements
  , loadSemanticEntityRows
  , loadSemanticRelationRows
  , loadSubsortRows
  , extendWithAuthorWorks
  , extendWithSemanticData
  , authorGFName
  , genericWorksGFName
  , workGFName
  ) where

import Data.List (nubBy)
import Metonymy.Ontology
import Metonymy.Types
import Text.Read (readMaybe)

data AuthorWorkRow = AuthorWorkRow
  { rowAuthorId :: EntityId
  , rowAuthorLabel :: String
  , rowWorkId :: EntityId
  , rowWorkLabel :: String
  , rowProvenance :: String
  }
  deriving stock (Eq, Show)

data SemanticEntityRow = SemanticEntityRow
  { semanticEntityId :: EntityId
  , semanticEntityLabel :: String
  , semanticEntityGF :: String
  , semanticEntitySorts :: [Sort]
  , semanticEntityProvenance :: String
  }
  deriving stock (Eq, Show)

data SemanticRelationRow = SemanticRelationRow
  { semanticRelation :: Relation
  , semanticRelationSource :: EntityId
  , semanticRelationTarget :: EntityId
  , semanticRelationProvenance :: String
  }
  deriving stock (Eq, Show)

data SubsortRow = SubsortRow
  { rowSubsort :: Sort
  , rowSupersort :: Sort
  , rowRuleName :: String
  , rowSubsortProvenance :: String
  }
  deriving stock (Eq, Show)

loadAuthorWorkRows :: FilePath -> IO [AuthorWorkRow]
loadAuthorWorkRows path = do
  contents <- readFile path
  case lines contents of
    [] -> fail ("empty author-work data file: " <> path)
    header : rows
      | header
          /= "author_id\tauthor_label\twork_id\twork_label\tprovenance" ->
          fail ("unexpected author-work header in " <> path)
      | otherwise -> traverse parseRow (zip [2 :: Int ..] rows)
  where
    parseRow (lineNumber, row) =
      case splitTabs row of
        [authorId, authorLabel, workId, workLabel, provenance] ->
          pure
            AuthorWorkRow
              { rowAuthorId = EntityId authorId
              , rowAuthorLabel = authorLabel
              , rowWorkId = EntityId workId
              , rowWorkLabel = workLabel
              , rowProvenance = provenance
              }
        _ ->
          fail
            ( path
                <> ":"
                <> show lineNumber
                <> ": expected five tab-separated fields"
            )

loadPredicates :: FilePath -> IO [Predicate]
loadPredicates path = do
  contents <- readFile path
  case lines contents of
    [] -> fail ("empty predicate data file: " <> path)
    header : rows
      | header
          /= "predicate_id\tlemma\tgf_function\tsubject_sort\tobject_sort\tstrength\tgf_expression\tprovenance" ->
          fail ("unexpected predicate header in " <> path)
      | otherwise -> traverse parsePredicate (zip [2 :: Int ..] rows)
  where
    parsePredicate (lineNumber, row) =
      case splitTabs row of
        [_identifier, lemma, gf, subjectSort, objectSort, strength, _gfExpression, provenance] -> do
          parsedSubject <- parseRequirementAt path lineNumber subjectSort
          parsedObject <- parseRequirementAt path lineNumber objectSort
          parsedStrength <- parseRead path lineNumber strength
          pure
            Predicate
              { predicateName = lemma
              , subjectRequirement = parsedSubject
              , objectRequirement = parsedObject
              , gfFunction = gf
              , predicateStrength = parsedStrength
              , predicateProvenance = provenance
              }
        _ -> malformed path lineNumber 8

loadActionRoleRequirements :: FilePath -> IO [ActionRoleRequirement]
loadActionRoleRequirements path = do
  contents <- readFile path
  case lines contents of
    [] -> fail ("empty action-role data file: " <> path)
    header : rows
      | header
          /= "action_id\tlemma\tframe_id\tthematic_role\thole_role\trequirement\tstrength\tmapping_status\tprovenance" ->
          fail ("unexpected action-role header in " <> path)
      | otherwise -> concat <$> traverse parseRole (zip [2 :: Int ..] rows)
  where
    parseRole (lineNumber, row) =
      case splitTabs row of
        [identifier, lemma, frameId, thematicRole, hole, requirement, strength, mappingStatus, provenance]
          | mappingStatus == "compiled" -> do
              parsedHole <- parseRead path lineNumber hole
              parsedRequirement <- parseRequirementAt path lineNumber requirement
              parsedStrength <- parseRead path lineNumber strength
              pure
                [ ActionRoleRequirement
                    { actionId = identifier
                    , actionLemma = lemma
                    , actionFrame = frameId
                    , actionThematicRole = thematicRole
                    , actionHoleRole = parsedHole
                    , actionRequirement = parsedRequirement
                    , actionStrength = parsedStrength
                    , actionProvenance = provenance
                    }
                ]
          | otherwise -> pure []
        _ -> malformed path lineNumber 9

loadSemanticEntityRows :: FilePath -> IO [SemanticEntityRow]
loadSemanticEntityRows path = do
  contents <- readFile path
  case lines contents of
    [] -> fail ("empty semantic entity data file: " <> path)
    header : rows
      | header /= "entity_id\tlabel\tgf_function\tsorts\tprovenance" ->
          fail ("unexpected semantic entity header in " <> path)
      | otherwise -> traverse parseEntity (zip [2 :: Int ..] rows)
  where
    parseEntity (lineNumber, row) =
      case splitTabs row of
        [identifier, label, gf, sorts, provenance] ->
          SemanticEntityRow
            (EntityId identifier)
            label
            gf
            <$> traverse (parseRead path lineNumber) (splitComma sorts)
            <*> pure provenance
        _ -> malformed path lineNumber 5

loadSemanticRelationRows :: FilePath -> IO [SemanticRelationRow]
loadSemanticRelationRows path = do
  contents <- readFile path
  case lines contents of
    [] -> fail ("empty semantic relation data file: " <> path)
    header : rows
      | header /= "relation\tsource\ttarget\tprovenance" ->
          fail ("unexpected semantic relation header in " <> path)
      | otherwise -> traverse parseRelation (zip [2 :: Int ..] rows)
  where
    parseRelation (lineNumber, row) =
      case splitTabs row of
        [relation, source, target, provenance] ->
          SemanticRelationRow
            <$> parseRead path lineNumber relation
            <*> pure (EntityId source)
            <*> pure (EntityId target)
            <*> pure provenance
        _ -> malformed path lineNumber 4

loadSubsortRows :: FilePath -> IO [SubsortRow]
loadSubsortRows path = do
  contents <- readFile path
  case lines contents of
    [] -> fail ("empty subsort data file: " <> path)
    header : rows
      | header /= "subsort\tsupersort\trule_name\tprovenance" ->
          fail ("unexpected subsort header in " <> path)
      | otherwise -> traverse parseSubsort (zip [2 :: Int ..] rows)
  where
    parseSubsort (lineNumber, row) =
      case splitTabs row of
        [subsort, supersort, ruleName, provenance] ->
          SubsortRow
            <$> parseRead path lineNumber subsort
            <*> parseRead path lineNumber supersort
            <*> pure ruleName
            <*> pure provenance
        _ -> malformed path lineNumber 4

extendWithAuthorWorks :: KnowledgeBase -> [AuthorWorkRow] -> KnowledgeBase
extendWithAuthorWorks base rows =
  base
    { entities = uniqueBy entityId (entities base <> generatedEntities)
    , typeAssertions =
        uniqueBy
          (\assertion -> (typedEntity assertion, assertedSort assertion))
          (typeAssertions base <> generatedTypes)
    , relationAssertions =
        uniqueBy
          ( \assertion ->
              ( assertedRelation assertion
              , relationSource assertion
              , relationTarget assertion
              )
          )
          (relationAssertions base <> generatedRelations)
    }
  where
    generatedEntities = concatMap rowEntities rows
    generatedTypes = concatMap rowTypes rows
    generatedRelations = concatMap rowRelations rows

    rowEntities row =
      [ EntityInfo
          (rowAuthorId row)
          (rowAuthorLabel row)
          (authorGFName (rowAuthorId row))
      , EntityInfo
          (genericWorksId (rowAuthorId row))
          (possessive (rowAuthorLabel row) <> " works")
          (genericWorksGFName (rowAuthorId row))
      , EntityInfo
          (rowWorkId row)
          (rowWorkLabel row)
          (workGFName (rowWorkId row))
      ]

    rowTypes row =
      [ typeAssertion row (rowAuthorId row) Writer
      , typeAssertion row (genericWorksId (rowAuthorId row)) LiteraryWork
      , typeAssertion row (genericWorksId (rowAuthorId row)) GenericReading
      , typeAssertion row (rowWorkId row) LiteraryWork
      ]

    rowRelations row =
      [ relationAssertion
          row
          (rowAuthorId row)
          (genericWorksId (rowAuthorId row))
      , relationAssertion row (rowAuthorId row) (rowWorkId row)
      ]

    typeAssertion row identifier sort =
      TypeAssertion
        identifier
        sort
        (LocalFact (factSource row <> ":type:" <> show sort))

    relationAssertion row source target =
      RelationAssertion
        Authored
        source
        target
        (LocalFact (factSource row <> ":relation:Authored"))

    factSource row =
      rowProvenance row
        <> ":"
        <> show (rowAuthorId row)
        <> ":"
        <> show (rowWorkId row)

extendWithSemanticData ::
  KnowledgeBase ->
  [SemanticEntityRow] ->
  [SemanticRelationRow] ->
  [SubsortRow] ->
  KnowledgeBase
extendWithSemanticData base entityRows relationRows subsortRows =
  base
    { entities =
        uniqueBy entityId (entities base <> map toEntity entityRows)
    , typeAssertions =
        uniqueBy
          (\assertion -> (typedEntity assertion, assertedSort assertion))
          (typeAssertions base <> concatMap toTypes entityRows)
    , relationAssertions =
        uniqueBy
          ( \assertion ->
              ( assertedRelation assertion
              , relationSource assertion
              , relationTarget assertion
              )
          )
          (relationAssertions base <> map toRelation relationRows)
    , subsortRules =
        uniqueBy
          (\(subsort, supersort, _) -> (subsort, supersort))
          (subsortRules base <> map toSubsort subsortRows)
    }
  where
    toEntity row =
      EntityInfo
        (semanticEntityId row)
        (semanticEntityLabel row)
        (semanticEntityGF row)

    toTypes row =
      [ TypeAssertion
          (semanticEntityId row)
          sort
          ( LocalFact
              ( semanticEntityProvenance row
                  <> ":type:"
                  <> show sort
              )
          )
      | sort <- semanticEntitySorts row
      ]

    toRelation row =
      RelationAssertion
        (semanticRelation row)
        (semanticRelationSource row)
        (semanticRelationTarget row)
        ( LocalFact
            ( semanticRelationProvenance row
                <> ":relation:"
                <> show (semanticRelation row)
            )
        )

    toSubsort row =
      ( rowSubsort row
      , rowSupersort row
      , rowRuleName row <> " [" <> rowSubsortProvenance row <> "]"
      )

genericWorksId :: EntityId -> EntityId
genericWorksId identifier =
  EntityId ("works-of-" <> unEntityId identifier)

authorGFName :: EntityId -> String
authorGFName identifier = "Author_" <> gfSuffix identifier

genericWorksGFName :: EntityId -> String
genericWorksGFName identifier = "Works_" <> gfSuffix identifier

workGFName :: EntityId -> String
workGFName identifier = "Work_" <> gfSuffix identifier

gfSuffix :: EntityId -> String
gfSuffix = map replaceInvalid . unEntityId
  where
    replaceInvalid character
      | character `elem` ['A' .. 'Z'] = character
      | character `elem` ['a' .. 'z'] = character
      | character `elem` ['0' .. '9'] = character
      | otherwise = '_'

possessive :: String -> String
possessive label
  | not (null label) && last label == 's' = label <> "'"
  | otherwise = label <> "'s"

uniqueBy :: Eq key => (value -> key) -> [value] -> [value]
uniqueBy key =
  nubBy (\left right -> key left == key right)

splitTabs :: String -> [String]
splitTabs =
  foldr step [""]
  where
    step '\t' fields = "" : fields
    step character (field : fields) = (character : field) : fields
    step _ [] = error "splitTabs invariant violated"

splitComma :: String -> [String]
splitComma value =
  case break (== ',') value of
    (field, []) -> [field]
    (field, _ : rest) -> field : splitComma rest

parseRead :: Read value => FilePath -> Int -> String -> IO value
parseRead path lineNumber value =
  case readMaybe value of
    Just parsed -> pure parsed
    Nothing ->
      fail
        ( path
            <> ":"
            <> show lineNumber
            <> ": unknown symbolic value "
            <> show value
        )

parseRequirementAt :: FilePath -> Int -> String -> IO Requirement
parseRequirementAt path lineNumber value =
  case readMaybe value of
    Just requirement -> pure requirement
    Nothing -> HasSort <$> parseRead path lineNumber value

malformed :: FilePath -> Int -> Int -> IO value
malformed path lineNumber expectedFields =
  fail
    ( path
        <> ":"
        <> show lineNumber
        <> ": expected "
        <> show expectedFields
        <> " tab-separated fields"
    )
